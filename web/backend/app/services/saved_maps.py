import hashlib
import io
import json
import logging
import math
import os
from pathlib import Path
import shutil
from uuid import uuid4
import warnings

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Literal
import yaml

from app.db.database import DATA_DIR
from app.models.saved_map import SavedMap

MAPS_DIR = Path(os.getenv("WRMS_MAPS_DIR", str(DATA_DIR / "maps"))).resolve()
MAX_YAML_BYTES = 64 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_CELLS = 4_000_000


class MapYaml(BaseModel):
    image: str = Field(min_length=1, max_length=1024)
    resolution: float = Field(gt=0, allow_inf_nan=False)
    origin: list[float] = Field(min_length=3, max_length=3)
    negate: Literal[0, 1]
    occupied_thresh: float = Field(gt=0, le=1, allow_inf_nan=False)
    free_thresh: float = Field(ge=0, lt=1, allow_inf_nan=False)
    mode: Literal["trinary", "scale", "raw"] = "trinary"
    model_config = ConfigDict(extra="ignore")

    @field_validator("origin")
    @classmethod
    def finite_origin(cls, value):
        if not all(math.isfinite(number) for number in value):
            raise ValueError("Origin must contain three finite numbers")
        return value

    @model_validator(mode="after")
    def ordered_thresholds(self):
        if self.free_thresh >= self.occupied_thresh:
            raise ValueError("Require free_thresh < occupied_thresh")
        return self


def parse_map(yaml_bytes, image_bytes, yaml_name, image_name):
    if not yaml_bytes or len(yaml_bytes) > MAX_YAML_BYTES:
        raise HTTPException(413, "YAML must be non-empty and at most 64 KiB")
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image must be non-empty and at most 20 MiB")
    if Path(yaml_name).suffix.lower() not in {".yaml", ".yml"}:
        raise HTTPException(422, "Select a .yaml or .yml file")
    suffix = Path(image_name).suffix.lower()
    if suffix not in {".pgm", ".png"}:
        raise HTTPException(422, "Select a .pgm or .png image")
    try:
        # ROS map metadata does not need YAML aliases or custom constructors.
        tokens = yaml.scan(yaml_bytes)
        if any(isinstance(t, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)) for t in tokens):
            raise ValueError("YAML anchors and aliases are not supported")
        config = MapYaml.model_validate(yaml.safe_load(yaml_bytes))
    except (yaml.YAMLError, UnicodeError, ValueError, RecursionError) as exc:
        raise HTTPException(422, "Invalid ROS map YAML: check resolution, origin, thresholds and mode") from exc
    # Only match the uploaded basename; never open a path or URL from YAML.
    if Path(config.image.replace("\\", "/")).name != Path(image_name.replace("\\", "/")).name:
        raise HTTPException(422, "YAML image must refer to the uploaded image filename")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(image_bytes)) as source:
                if (suffix == ".png" and source.format != "PNG") or (
                    suffix == ".pgm" and (source.format != "PPM" or image_bytes[:2] not in {b"P2", b"P5"})
                ):
                    raise ValueError("Image content does not match the extension")
                width, height = source.size
                if width * height > MAX_CELLS:
                    raise HTTPException(413, "Map must contain at most 4,000,000 cells")
                if getattr(source, "n_frames", 1) != 1 or source.mode not in {"1", "L", "LA", "P", "RGB", "RGBA"}:
                    raise ValueError("Use a single-frame 8-bit PGM/PNG image")
                source.load()
                gray = source.convert("L")
                alpha = source.convert("RGBA").getchannel("A")
                pixels = gray.tobytes()
                opacity = alpha.tobytes()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(422, "Invalid or unsupported PGM/PNG image") from exc

    data = []
    # Image rows start at the top; OccupancyGrid rows start at the bottom.
    for row in range(height - 1, -1, -1):
        for column in range(width):
            index = row * width + column
            pixel = pixels[index]
            if config.mode == "raw":
                value = pixel if pixel <= 100 else -1
            elif opacity[index] < 255:
                value = -1
            else:
                probability = (pixel if config.negate else 255 - pixel) / 255
                if probability >= config.occupied_thresh:
                    value = 100
                elif probability <= config.free_thresh:
                    value = 0
                elif config.mode == "scale":
                    value = math.floor(100 * (probability - config.free_thresh) /
                                       (config.occupied_thresh - config.free_thresh) + 0.5)
                else:
                    value = -1
            data.append(value)
    metadata = dict(
        width=width, height=height, resolution=config.resolution,
        origin=dict(zip(("x", "y", "yaw"), config.origin)), frame_id="map",
        mode=config.mode, negate=config.negate, free_thresh=config.free_thresh,
        occupied_thresh=config.occupied_thresh,
    )
    digest = hashlib.sha256(json.dumps([metadata, data], separators=(",", ":")).encode()).hexdigest()
    grid = {**metadata, "map_hash": digest, "data": data}
    return config, grid


def describe(record):
    return dict(id=record.id, name=record.name, is_selected=record.is_selected,
                created_at=record.created_at, **record.metadata_json)


def load_grid(record):
    try:
        grid = json.loads((MAPS_DIR / record.id / "grid.json").read_text())
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "Saved map files are unavailable; restore the map backup") from exc
    return {**grid, **describe(record)}


def save_map(db, yaml_bytes, image_bytes, yaml_name, image_name, name):
    config, grid = parse_map(yaml_bytes, image_bytes, yaml_name, image_name)
    map_id = uuid4().hex
    folder = MAPS_DIR / map_id
    folder.mkdir(parents=True)
    record = SavedMap(id=map_id, name=name,
                      metadata_json={key: value for key, value in grid.items() if key != "data"})
    try:
        stored_image = "map" + Path(image_name).suffix.lower()
        (folder / stored_image).write_bytes(image_bytes)
        metadata = config.model_dump()
        metadata["image"] = stored_image
        (folder / "map.yaml").write_text(yaml.safe_dump(metadata), encoding="utf-8")
        (folder / "grid.json").write_text(json.dumps(grid, separators=(",", ":")), encoding="utf-8")
        db.add(record)
        db.commit()
    except Exception:
        db.rollback()
        shutil.rmtree(folder)
        raise
    db.refresh(record)
    return describe(record)


def delete_files(map_id):
    try:
        shutil.rmtree(MAPS_DIR / map_id)
    except FileNotFoundError:
        pass
    except OSError:
        logging.getLogger(__name__).exception("Deleted map metadata; could not remove files for %s", map_id)

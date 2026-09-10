from typing import Literal

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    product_code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    image_path: str | None = Field(default=None, max_length=255)
    status: Literal["AVAILABLE", "UNAVAILABLE"] = "AVAILABLE"
    default_rack_id: int


class ProductUpdate(BaseModel):
    product_code: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    image_path: str | None = Field(default=None, max_length=255)
    status: Literal["AVAILABLE", "UNAVAILABLE"] | None = None
    default_rack_id: int | None = None


class ProductOut(BaseModel):
    id: int
    product_code: str
    name: str
    image_path: str | None
    status: str

    default_rack_id: int
    default_rack_code: str
    default_rack_name: str

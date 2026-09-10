from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.models.line_segment import LineSegment
from app.models.location import Location
from app.models.product import Product
from app.models.task import Task
from app.schemas.location import LocationCreate, LocationOut, LocationUpdate


router = APIRouter(
    prefix="/locations",
    tags=["Locations"],
)


def location_in_use(db: Session, location_id: int):
    return any([
        db.scalar(
            select(Product.id).where(Product.default_rack_id == location_id)
        ),
        db.scalar(
            select(Task.id).where(
                or_(
                    Task.pickup_location_id == location_id,
                    Task.dropoff_location_id == location_id,
                )
            )
        ),
        db.scalar(
            select(LineSegment.id).where(
                or_(
                    LineSegment.start_location_id == location_id,
                    LineSegment.end_location_id == location_id,
                )
            )
        ),
    ])


def save_location(db: Session, location: Location):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Location code already exists or location is in use",
        ) from exc

    db.refresh(location)
    return location


@router.get("", response_model=list[LocationOut])
def get_locations(db: Session = Depends(get_db)):
    return db.scalars(select(Location).order_by(Location.id)).all()


@router.get("/{location_id}", response_model=LocationOut)
def get_location(location_id: int, db: Session = Depends(get_db)):
    location = db.get(Location, location_id)

    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")

    return location


@router.post("", response_model=LocationOut, status_code=201)
def create_location(data: LocationCreate, db: Session = Depends(get_db)):
    location = Location(**data.model_dump())
    db.add(location)
    return save_location(db, location)


@router.patch("/{location_id}", response_model=LocationOut)
def update_location(
    location_id: int,
    data: LocationUpdate,
    db: Session = Depends(get_db),
):
    location = db.get(Location, location_id)

    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")

    changes = data.model_dump(exclude_unset=True)

    if (
        changes.get("location_type") not in (None, location.location_type)
        and location_in_use(db, location.id)
    ):
        raise HTTPException(
            status_code=409,
            detail="Location type cannot change while location is in use",
        )

    if changes.get("is_active") is False and location_in_use(db, location.id):
        raise HTTPException(
            status_code=409,
            detail="Location is in use and cannot be deactivated",
        )

    for field, value in changes.items():
        setattr(location, field, value)

    return save_location(db, location)


@router.delete("/{location_id}", status_code=204)
def delete_location(location_id: int, db: Session = Depends(get_db)):
    location = db.get(Location, location_id)

    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")

    if location_in_use(db, location.id):
        raise HTTPException(
            status_code=409,
            detail="Location is in use and cannot be deleted",
        )

    db.delete(location)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Location cannot be deleted",
        ) from exc

    return Response(status_code=204)

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.models.location import Location
from app.models.product import Product
from app.models.task import Task
from app.schemas.product import ProductCreate, ProductOut, ProductUpdate


router = APIRouter(
    prefix="/products",
    tags=["Products"],
)


def get_rack(db: Session, rack_id: int):
    rack = db.get(Location, rack_id)

    if rack is None:
        raise HTTPException(status_code=404, detail="Rack not found")

    if rack.location_type != "RACK":
        raise HTTPException(
            status_code=400,
            detail="Product must be assigned to a rack",
        )

    if not rack.is_active:
        raise HTTPException(status_code=400, detail="Rack is inactive")

    return rack


def build_product_response(product: Product, rack: Location):
    return {
        "id": product.id,
        "product_code": product.product_code,
        "name": product.name,
        "image_path": product.image_path,
        "status": product.status,
        "default_rack_id": rack.id,
        "default_rack_code": rack.code,
        "default_rack_name": rack.name,
    }


def save_product(db: Session, product: Product):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "product_code" in str(exc).lower():
            raise HTTPException(
                status_code=409,
                detail="Product code already exists",
            ) from exc
        raise HTTPException(
            status_code=409,
            detail="Product cannot be saved",
        ) from exc

    db.refresh(product)
    return build_product_response(
        product,
        db.get(Location, product.default_rack_id),
    )


@router.get("", response_model=list[ProductOut])
def get_products(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Product, Location)
        .join(Location, Product.default_rack_id == Location.id)
        .order_by(Product.id)
    ).all()

    return [
        build_product_response(product, rack)
        for product, rack in rows
    ]


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return build_product_response(
        product,
        db.get(Location, product.default_rack_id),
    )


@router.post("", response_model=ProductOut, status_code=201)
def create_product(data: ProductCreate, db: Session = Depends(get_db)):
    get_rack(db, data.default_rack_id)

    product = Product(**data.model_dump())
    db.add(product)
    return save_product(db, product)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    data: ProductUpdate,
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    changes = data.model_dump(exclude_unset=True)

    if "default_rack_id" in changes:
        get_rack(db, changes["default_rack_id"])

    for field, value in changes.items():
        setattr(product, field, value)

    return save_product(db, product)


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    if db.scalar(
        select(Task.id).where(Task.product_id == product.id)
    ) is not None:
        raise HTTPException(
            status_code=409,
            detail="Product is used by a task and cannot be deleted",
        )

    db.delete(product)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Product cannot be deleted",
        ) from exc

    return Response(status_code=204)

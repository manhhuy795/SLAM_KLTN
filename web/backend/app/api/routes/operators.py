from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.models.operator import Operator
from app.schemas.operator import OperatorOut


router = APIRouter(
    prefix="/operators",
    tags=["Operators"],
)


@router.get("", response_model=list[OperatorOut])
def get_operators(db: Session = Depends(get_db)):
    return db.scalars(
        select(Operator)
        .where(Operator.is_active.is_(True))
        .order_by(Operator.id)
    ).all()

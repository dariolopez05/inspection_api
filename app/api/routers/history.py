from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models.inspection import Inspection
from app.schemas.inspection import InspectionRead

router = APIRouter(tags=["inspection"])


@router.get("/history/{plate_number}", response_model=list[InspectionRead])
def history(plate_number: str, db: Session = Depends(get_db)) -> list[Inspection]:
    stmt = (
        select(Inspection)
        .where(Inspection.plate_number == plate_number)
        .order_by(Inspection.created_at.desc())
    )
    return list(db.scalars(stmt).all())

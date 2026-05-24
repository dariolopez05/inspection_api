from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models.inspection import Inspection
from app.schemas.inspection import InspectionPage

router = APIRouter(tags=["inspection"])


@router.get("/history/{plate_number}", response_model=InspectionPage)
def history(
    plate_number: str,
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> InspectionPage:
    base = select(Inspection).where(Inspection.plate_number == plate_number)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    stmt = base.order_by(Inspection.created_at.desc()).limit(limit).offset(offset)
    items = list(db.scalars(stmt).all())
    return InspectionPage(items=items, total=total, limit=limit, offset=offset)

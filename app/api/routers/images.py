from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.db.models.inspection import Inspection
from app.schemas.inspection import ImageURL
from app.storage.s3 import generate_presigned_url

router = APIRouter(tags=["inspection"])


@router.get("/inspections/{inspection_id}/image", response_model=ImageURL)
def inspection_image(
    inspection_id: int, request: Request, db: Session = Depends(get_db)
) -> ImageURL:
    record = db.get(Inspection, inspection_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inspeccion no encontrada.")
    if not record.image_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La inspeccion no tiene imagen asociada.")

    expires_in = get_settings().s3_presigned_expiry
    url = generate_presigned_url(
        request.app.state.s3_public, request.app.state.s3_bucket, record.image_key, expires_in
    )
    return ImageURL(url=url, expires_in=expires_in)

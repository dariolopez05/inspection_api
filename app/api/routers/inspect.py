from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_db
from app.db.models.inspection import Inspection
from app.ml.classifier import predict
from app.ml.preprocessing import preprocess_image
from app.schemas.inspection import InspectionResult
from app.storage.s3 import object_key, upload_image

router = APIRouter(tags=["inspection"])


@router.post("/inspect", response_model=InspectionResult, status_code=status.HTTP_201_CREATED)
async def inspect(
    request: Request,
    plate_number: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> InspectionResult:
    model = request.app.state.model
    if model is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Modelo no disponible.")

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El archivo debe ser una imagen.")

    raw = await file.read()
    try:
        tensor = preprocess_image(raw)
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Imagen invalida.") from exc

    is_damaged, confidence = await run_in_threadpool(predict, model, tensor)

    record = Inspection(plate_number=plate_number, is_damaged=is_damaged, confidence=confidence)
    db.add(record)
    db.commit()
    db.refresh(record)

    key = object_key(plate_number, record.id, file.content_type)
    await run_in_threadpool(
        upload_image, request.app.state.s3, request.app.state.s3_bucket, key, raw, file.content_type
    )
    record.image_key = key
    db.commit()
    db.refresh(record)

    return InspectionResult(
        plate_number=record.plate_number,
        is_damaged=record.is_damaged,
        confidence=record.confidence,
        image_key=record.image_key,
    )

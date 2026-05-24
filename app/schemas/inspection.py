from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InspectionResult(BaseModel):
    plate_number: str
    is_damaged: bool
    confidence: float
    image_key: str | None = None


class InspectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plate_number: str
    is_damaged: bool
    confidence: float
    image_key: str | None = None
    created_at: datetime


class ImageURL(BaseModel):
    url: str
    expires_in: int

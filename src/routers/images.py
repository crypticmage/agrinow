"""
images.py — FastAPI router for the `images` table.

Handles:
    POST   /images/           Upload, compress (Pillow) and store image BLOB
    GET    /images/           List metadata of all stored images
    GET    /images/{image_id} Stream the image back to the browser
"""

import io
import base64
from typing import Annotated, List, Optional
from datetime import datetime

from PIL import Image
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from starlette import status

from database.database import SessionLocal   # SQLAlchemy session (from database.py)
from models import Images, ImagesTemplate    # ORM models (from models.py)
from dependencies import get_current_user    # JWT auth dependency


# ─────────────────────────────────────────────────────────────────────────────
#  Compression settings (Pillow)
#  JPEG  quality 90  → near-lossless
#  PNG   lossless recompression
#  WEBP  quality 90  → near-lossless
#  GIF   preserved as-is
# ─────────────────────────────────────────────────────────────────────────────
_COMPRESS_SETTINGS: dict[str, dict] = {
    "JPEG": {"quality": 90, "optimize": True, "progressive": True},
    "PNG":  {"optimize": True, "compress_level": 6},
    "WEBP": {"quality": 90, "method": 6},
    "GIF":  {},
}


def _compress(raw_bytes: bytes, fmt_hint: str = "JPEG") -> tuple[bytes, str, int]:
    """
    Compress raw image bytes in-memory using Pillow.

    Args:
        raw_bytes : bytes read directly from the uploaded UploadFile
        fmt_hint  : uppercase format string derived from Content-Type / filename
                    ('JPEG', 'PNG', 'WEBP', 'GIF').  Pillow overrides this if
                    it can detect the real format from the stream header.

    Returns:
        (compressed_bytes, detected_format, size_in_bytes)
    """
    fmt = fmt_hint.upper()
    if fmt == "JPG":
        fmt = "JPEG"

    with Image.open(io.BytesIO(raw_bytes)) as img:
        # Let Pillow auto-detect the real format from the byte stream
        if img.format:
            fmt = img.format.upper()

        # JPEG cannot hold an alpha channel — convert RGBA / palette images
        if fmt == "JPEG" and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        kwargs = _COMPRESS_SETTINGS.get(fmt, {})
        buf = io.BytesIO()
        img.save(buf, format=fmt, **kwargs)
        compressed_bytes = buf.getvalue()

    return compressed_bytes, fmt, len(compressed_bytes)


def _fmt_from_upload(file: UploadFile) -> str:
    """Derive a Pillow-compatible format string from Content-Type or filename."""
    if file.content_type:
        ext = file.content_type.split("/")[-1].upper()
        return "JPEG" if ext == "JPG" else ext
    if file.filename and "." in file.filename:
        ext = file.filename.rsplit(".", 1)[-1].upper()
        return "JPEG" if ext == "JPG" else ext
    return "JPEG"


# ─────────────────────────────────────────────────────────────────────────────
#  Router setup
# ─────────────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/images", tags=["Images"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]


# ─────────────────────────────────────────────────────────────────────────────
#  Pydantic response schema  (metadata only — no blob)
# ─────────────────────────────────────────────────────────────────────────────
class ImageMeta(BaseModel):
    id:         int
    file_name:  Optional[str]
    format:     Optional[str]
    size:       Optional[int]
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
#  POST /images/
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=ImageMeta,
    summary="Upload & compress an image",
    description=(
        "Accepts a multipart image upload, compresses it in-memory with Pillow, "
        "stores the resulting BLOB in the `images` table, and returns the row metadata."
    ),
)
async def upload_image(db: db_dependency, file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    # 1. Read raw bytes from the HTTP upload
    raw_bytes = await file.read()

    # 2. Compress in-memory with Pillow
    try:
        compressed_bytes, detected_fmt, compressed_size = _compress(
            raw_bytes, fmt_hint=_fmt_from_upload(file)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image compression failed: {exc}",
        )

    # 3. Persist BLOB + metadata to the `images` table via SQLAlchemy
    record = Images(
        file_name=file.filename,
        data=compressed_bytes,
        format=detected_fmt[:10],   # VARCHAR(10) in models.py
        size=compressed_size,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # 4. Generate base64 thumbnail (256x256) and store in `images_template`
    try:
        with Image.open(io.BytesIO(compressed_bytes)) as img:
            thumb_fmt = detected_fmt.upper()
            if thumb_fmt == "JPEG" and img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail((256, 256))
            thumb_buf = io.BytesIO()
            img.save(thumb_buf, format=thumb_fmt, **_COMPRESS_SETTINGS.get(thumb_fmt, {}))
            thumb_bytes = thumb_buf.getvalue()
            thumb_b64 = base64.b64encode(thumb_bytes).decode("utf-8")

        thumb_record = ImagesTemplate(
            image_id=record.id,
            file_name=file.filename,
            data=thumb_b64,
            format=detected_fmt[:10],
            size=len(thumb_bytes),
        )
        db.add(thumb_record)
        db.commit()
    except Exception:
        pass  # thumbnail generation failure should not block the upload

    return record


# ─────────────────────────────────────────────────────────────────────────────
#  GET /images/list  — list all (metadata only)
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/list",
    response_model=List[ImageMeta],
    status_code=status.HTTP_200_OK,
    summary="List all stored images",
    description=(
        "Returns metadata (id, file_name, format, size, created_at) for every row "
        "in the `images` table. No BLOB data is sent — use GET /images/{id} to "
        "stream the actual image."
    ),
)
# def list_images(db: db_dependency, skip: int = 0, limit: int = 100, current_user: dict = Depends(get_current_user)):
#     return db.query(Images).order_by(Images.id).offset(skip).limit(limit).all()

@router.get("/list", response_model=List[ImageMeta], status_code=status.HTTP_200_OK)
def list_images(
    db: db_dependency,
    skip: int = 0,
    limit: int = 100,
    current_user: dict = Depends(get_current_user), summary="List all stored images",
    description=(
        "Returns metadata (id, file_name, format, size, created_at) for every row "
        "in the `images` table. No BLOB data is sent — use GET /images/{id} to "
        "stream the actual image."
    ),
):
    rows = (
        db.query(
            Images.id,
            Images.file_name,
            Images.format,
            Images.size,
            Images.created_at,
        )
        .order_by(Images.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [ImageMeta.model_validate(row._asdict()) for row in rows]


# ─────────────────────────────────────────────────────────────────────────────
#  GET /images/base/{image_id}  — fast base64 thumbnail preview
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/base/{image_id}",
    status_code=status.HTTP_200_OK,
    summary="Get base64 thumbnail for fast preview",
    description=(
        "Returns the base64-encoded thumbnail from `images_template` for fast "
        "preview rendering. Much lighter than streaming the full HD BLOB."
    ),
)
async def get_image_base(
    image_id: int,
    db: db_dependency,
    current_user: dict = Depends(get_current_user),
):
    row = (
        db.query(ImagesTemplate.data, ImagesTemplate.format)
        .filter(ImagesTemplate.image_id == image_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No thumbnail found for image id={image_id}",
        )

    fmt = (row.format or "jpeg").lower().replace("jpg", "jpeg")
    return {
        "image_id": image_id,
        "format": fmt,
        "data_uri": f"data:image/{fmt};base64,{row.data}",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  GET /images/{image_id}  — stream the actual HD image
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{image_id}"  ,  summary="Stream an image by ID",
    description=(
        "Fetches the BLOB from the `images` table and returns it as a binary "
        "image response — renders directly in the browser."
    ),
    responses={
        200: {"content": {"image/*": {}}, "description": "Raw image bytes"},
        404: {"description": "Image not found"},
    },)
async def get_image(
    image_id: int,
    db: db_dependency,
    current_user: dict = Depends(get_current_user),
):
    row = (
        db.query(Images.data, Images.format)
        .filter(Images.id == image_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No image found with id={image_id}")

    fmt = (row.format or "jpeg").lower().replace("jpg", "jpeg")
    return Response(content=row.data, media_type=f"image/{fmt}")

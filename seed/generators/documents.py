"""Sample document generation: PDF/PNG, "SAMPLE" watermarked, uploaded to
MinIO under bucket `clearquote-demo-docs` (spec.md scope item 5, AC6).

Not real documents -- reportlab/Pillow-drawn placeholders, per the item's
"Notes for the agent" (WeasyPrint stays CQ-020's letter renderer).
"""

from __future__ import annotations

import io
import uuid

import boto3
from botocore.exceptions import ClientError
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from app.core.config import get_settings

DEMO_DOCS_BUCKET = "clearquote-demo-docs"

# Deterministic watermark color + coordinates so tests can assert an exact
# burned-in pixel without OCR (documented in plan.md decision -- see
# `seed/tests/test_documents_watermarked.py`).
_WATERMARK_RGB = (200, 30, 30)
_PNG_SIZE = (800, 600)


def get_s3_client() -> boto3.client:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


def ensure_demo_docs_bucket(s3_client: boto3.client) -> None:
    """Idempotently creates `clearquote-demo-docs` -- `infra/docker-compose.yml`'s
    `minio-init` only creates the `clear-quote` bucket CQ-004's app uses
    (plan.md decision #7)."""
    try:
        s3_client.head_bucket(Bucket=DEMO_DOCS_BUCKET)
    except ClientError:
        s3_client.create_bucket(Bucket=DEMO_DOCS_BUCKET)


def generate_sample_pdf(title: str) -> bytes:
    """A one-page PDF with a large diagonal "SAMPLE" watermark burned into
    the page content (readable back via `pypdf`'s text extraction)."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=LETTER)
    width, height = LETTER

    c.setFont("Helvetica", 14)
    c.drawString(72, height - 100, title)
    c.drawString(72, height - 130, "Clear Quote demo document -- not a real record.")

    c.saveState()
    c.translate(width / 2, height / 2)
    c.rotate(45)
    c.setFillColor(HexColor("#c81e1e"))
    c.setFillAlpha(0.35)
    c.setFont("Helvetica-Bold", 80)
    c.drawCentredString(0, 0, "SAMPLE")
    c.restoreState()

    c.showPage()
    c.save()
    return buffer.getvalue()


def generate_sample_png(title: str) -> bytes:
    """A placeholder PNG with a burned-in diagonal "SAMPLE" band at a fixed,
    deterministic color/position so a test can assert the exact pixel
    without OCR."""
    image = Image.new("RGB", _PNG_SIZE, color=(245, 245, 245))
    draw = ImageDraw.Draw(image, "RGBA")

    # Deterministic diagonal band across the full image -- guaranteed to
    # cover the image center regardless of font availability.
    band_half_width = 60
    draw.polygon(
        [
            (0, _PNG_SIZE[1] // 2 - band_half_width),
            (_PNG_SIZE[0], _PNG_SIZE[1] // 2 + _PNG_SIZE[0] // 3 - band_half_width),
            (_PNG_SIZE[0], _PNG_SIZE[1] // 2 + _PNG_SIZE[0] // 3 + band_half_width),
            (0, _PNG_SIZE[1] // 2 + band_half_width),
        ],
        fill=(*_WATERMARK_RGB, 255),
    )

    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    try:
        font = ImageFont.truetype("Helvetica.ttc", 60)
    except OSError:
        font = ImageFont.load_default()
    text_xy = (_PNG_SIZE[0] // 2 - 120, _PNG_SIZE[1] // 2 - 20)
    draw.text(text_xy, "SAMPLE", fill=(*_WATERMARK_RGB, 255), font=font)
    draw.text((20, 20), title, fill=(60, 60, 60, 255))

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def watermark_pixel_check_point() -> tuple[int, int]:
    """The exact (x, y) `test_documents_watermarked.py` reads back and
    compares against `_WATERMARK_RGB` -- guaranteed inside the diagonal band
    drawn by `generate_sample_png` at its left edge."""
    return (5, _PNG_SIZE[1] // 2)


def watermark_rgb() -> tuple[int, int, int]:
    return _WATERMARK_RGB


def upload_sample_document(
    s3_client: boto3.client,
    *,
    application_id: uuid.UUID,
    doc_type: str,
    content: bytes,
    ext: str,
) -> str:
    """Uploads `content` and returns the MinIO object key. Key ends in
    `-SAMPLE.<ext>` (AC6's filename-suffix check)."""
    object_key = f"applications/{application_id}/{doc_type}-SAMPLE.{ext}"
    content_type = "application/pdf" if ext == "pdf" else "image/png"
    s3_client.put_object(
        Bucket=DEMO_DOCS_BUCKET, Key=object_key, Body=content, ContentType=content_type
    )
    return object_key

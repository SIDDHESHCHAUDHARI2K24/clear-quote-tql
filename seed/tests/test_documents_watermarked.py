"""AC6: every persona has at least one `documents` row pointing at a MinIO
object under bucket `clearquote-demo-docs`, and the stored file is
watermarked "SAMPLE" -- both by filename suffix and a burned-in watermark on
the page. Runs against the real (shared) MinIO container (`make up`)."""

import io
import uuid

from PIL import Image
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.applications.assets.models import Document
from seed.generators.documents import (
    DEMO_DOCS_BUCKET,
    ensure_demo_docs_bucket,
    generate_sample_pdf,
    generate_sample_png,
    get_s3_client,
    upload_sample_document,
    watermark_pixel_check_point,
    watermark_rgb,
)
from seed.loader import load_persona_fixtures, seed_persona, seed_providers, seed_users


def test_generated_pdf_has_sample_watermark_text() -> None:
    pdf_bytes = generate_sample_pdf("Test Persona -- Pay Stub")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = reader.pages[0].extract_text()
    assert "SAMPLE" in text


def test_generated_png_has_burned_in_sample_pixel() -> None:
    png_bytes = generate_sample_png("Test Persona -- Bank Statement")
    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    assert image.getpixel(watermark_pixel_check_point()) == watermark_rgb()


def test_upload_sample_document_key_has_sample_suffix_and_round_trips_via_minio() -> None:
    s3_client = get_s3_client()
    ensure_demo_docs_bucket(s3_client)
    application_id = uuid.uuid4()

    pdf_key = upload_sample_document(
        s3_client,
        application_id=application_id,
        doc_type="pay_stub",
        content=generate_sample_pdf("Round Trip Test"),
        ext="pdf",
    )
    assert pdf_key.endswith("-SAMPLE.pdf")

    obj = s3_client.get_object(Bucket=DEMO_DOCS_BUCKET, Key=pdf_key)
    body = obj["Body"].read()
    reader = PdfReader(io.BytesIO(body))
    assert "SAMPLE" in reader.pages[0].extract_text()

    png_key = upload_sample_document(
        s3_client,
        application_id=application_id,
        doc_type="bank_statement",
        content=generate_sample_png("Round Trip Test"),
        ext="png",
    )
    assert png_key.endswith("-SAMPLE.png")
    png_obj = s3_client.get_object(Bucket=DEMO_DOCS_BUCKET, Key=png_key)
    image = Image.open(io.BytesIO(png_obj["Body"].read())).convert("RGB")
    assert image.getpixel(watermark_pixel_check_point()) == watermark_rgb()


async def test_every_persona_gets_at_least_one_documents_row(db_session: AsyncSession) -> None:
    s3_client = get_s3_client()
    ensure_demo_docs_bucket(s3_client)

    user_result = await seed_users(db_session)
    await seed_providers(db_session)

    personas = load_persona_fixtures()
    for i, persona in enumerate(personas):
        lo_id = user_result.lo_ids[i % len(user_result.lo_ids)]
        result = await seed_persona(db_session, persona, lo_id=lo_id, s3_client=s3_client)

        documents = (
            (
                await db_session.execute(
                    select(Document).where(Document.application_id == result.application_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(documents) >= 1, f"{persona['key']} has no documents row"
        for doc in documents:
            assert doc.object_key.endswith("-SAMPLE.pdf") or doc.object_key.endswith("-SAMPLE.png")
            obj = s3_client.get_object(Bucket=DEMO_DOCS_BUCKET, Key=doc.object_key)
            assert obj["ContentLength"] > 0

"""The old JSON import must not bypass source-evidence verification."""

from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.models.document_extraction import DocumentExtractionResult
from app.services.document_extraction_import_service import DocumentExtractionImportService


@pytest.mark.asyncio
async def test_direct_extraction_import_is_disabled() -> None:
    service = DocumentExtractionImportService(object())  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="Direct extraction import is disabled"):
        await service.import_extraction(
            patient_id=uuid4(),
            uploaded_by=uuid4(),
            uploaded_by_role="patient",
            extraction=DocumentExtractionResult(),
        )

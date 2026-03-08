"""Document upload, AI parsing, and explanation."""


class DocumentService:

    async def upload(self, patient_id: str, file_data: bytes, metadata: dict) -> dict:
        raise NotImplementedError

    async def list_documents(self, patient_id: str) -> list:
        raise NotImplementedError

    async def get_document(self, document_id: str) -> dict:
        raise NotImplementedError

    async def explain(self, document_id: str, language: str = "en") -> str:
        """Ask AI to explain a document in plain language."""
        raise NotImplementedError

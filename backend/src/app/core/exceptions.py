"""Custom exception hierarchy — catch `MediAgentError` to handle all app errors uniformly."""


class MediAgentError(Exception):
    """Base. All app exceptions carry `message` and `code`."""

    def __init__(self, message: str = "Something went wrong", code: str = "INTERNAL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class NotFoundError(MediAgentError):
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            message=f"{resource} '{identifier}' not found",
            code="NOT_FOUND",
        )


class AuthenticationError(MediAgentError):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message=message, code="AUTHENTICATION_ERROR")


class AuthorizationError(MediAgentError):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message=message, code="AUTHORIZATION_ERROR")


class ValidationError(MediAgentError):
    """Business rule violation — not Pydantic schema validation."""

    def __init__(self, message: str):
        super().__init__(message=message, code="VALIDATION_ERROR")


class ExternalServiceError(MediAgentError):
    """Gemini, Deepgram, Supabase, etc. — any external call failure."""

    def __init__(self, service: str, message: str = ""):
        super().__init__(
            message=f"{service} error: {message}" if message else f"{service} is unavailable",
            code="EXTERNAL_SERVICE_ERROR",
        )


class DocumentParseError(MediAgentError):
    """AI failed to extract structured data from a document."""

    def __init__(self, document_id: str, message: str = ""):
        super().__init__(
            message=f"Failed to parse document '{document_id}': {message}",
            code="DOCUMENT_PARSE_ERROR",
        )


class AgentError(MediAgentError):
    """Base exception for all agent errors."""

    pass


class LLMError(AgentError):
    """Raised when LLM generation fails."""

    pass


class ParsingError(AgentError):
    """Raised when document parsing fails."""

    pass


class NormalizationError(AgentError):
    """Raised when data normalization fails."""

    pass

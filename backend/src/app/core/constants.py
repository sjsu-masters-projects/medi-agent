"""App-wide constants."""

# API
API_V1_PREFIX = "/api/v1"

# File uploads
MAX_FILE_SIZE_MB = 25
ALLOWED_DOCUMENT_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp"}

# LLM models
DEFAULT_LLM_MODEL = "gemini-2.0-flash"
REASONING_LLM_MODEL = "gemini-2.0-pro"
MAX_CHAT_HISTORY_MESSAGES = 50

# Clinical thresholds
NARANJO_THRESHOLD_PROBABLE = 5
NARANJO_THRESHOLD_DEFINITE = 9
ADHERENCE_CRITICAL_THRESHOLD = 0.7  # below this = "at risk"

# Pagination
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

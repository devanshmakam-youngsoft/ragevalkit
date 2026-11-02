"""Fixed values: the library's names, defaults, limits and the kinds of things it knows about (case types, question categories)."""

from ragevalkit.core.constants.case_types import is_non_rag
from ragevalkit.core.constants.document_reading import (
    MAX_PAGES,
    MAX_UNPACKED_BYTES,
    MIN_TEXT_CHARS,
    MIN_USABLE_CHARS,
    SUPPORTED_MESSAGE,
    SUPPORTED_SUFFIXES,
    TARGET_CHARS,
)
from ragevalkit.core.constants.generator_categories import (
    CASE_TYPE,
    CATEGORIES,
    CATEGORY_LABELS,
    DEFAULT_PER_CATEGORY,
    DEFAULT_TURNS,
    MAX_TURNS,
    MIN_TURNS,
)
from ragevalkit.core.constants.library import (
    API_TITLE,
    DATA_DIR_NAME,
    DISPLAY_NAME,
    LIBRARY_NAME,
    LOGGER_NAME,
    LOGS_DIR_NAME,
    SESSION_COOKIE_NAME,
    STORE_FILE_NAME,
    TEMP_FOLDER_PREFIX,
    UPLOADS_DIR_NAME,
)
from ragevalkit.core.constants.recommendation_defaults import (
    DEFAULT_ANSWER_WEIGHT,
    DEFAULT_MATERIAL_WEIGHT,
    DEFAULT_MIN_QUALITY,
    DEFAULT_TOLERANCE,
    MIN_SHARED_SHARE,
)

__all__ = [
    "API_TITLE", "CASE_TYPE", "CATEGORIES", "CATEGORY_LABELS", "DATA_DIR_NAME", "DEFAULT_ANSWER_WEIGHT",
    "DEFAULT_MATERIAL_WEIGHT", "DEFAULT_MIN_QUALITY", "DEFAULT_PER_CATEGORY", "DEFAULT_TOLERANCE",
    "DEFAULT_TURNS", "DISPLAY_NAME", "LIBRARY_NAME", "LOGGER_NAME", "LOGS_DIR_NAME", "MAX_PAGES",
    "MAX_TURNS", "MAX_UNPACKED_BYTES", "MIN_SHARED_SHARE", "MIN_TEXT_CHARS", "MIN_TURNS",
    "MIN_USABLE_CHARS", "SESSION_COOKIE_NAME", "STORE_FILE_NAME", "SUPPORTED_MESSAGE",
    "SUPPORTED_SUFFIXES", "TARGET_CHARS", "TEMP_FOLDER_PREFIX", "UPLOADS_DIR_NAME", "is_non_rag"
]

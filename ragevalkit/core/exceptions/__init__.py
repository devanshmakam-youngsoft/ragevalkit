"""Every error the library raises. They all inherit from ``RagevalError``, one file per area.

    base                   RagevalError, ConfigError, InvalidInput, NotFoundError, TooLargeError
    spreadsheet_loader     DatasetError
    document_reader        DocumentError
    db_services            StoreError, VersionNotFound, ConflictError, GroupNotFound
    evaluation_runner      RunError, RunBusy, NoDatasetError
    testcase_generator     GenerationError, GenerationBusy
    answer_judge           JudgeError

``handlers.py`` turns an error into the HTTP answer the dashboard shows. The supported way for library users to import
an error is from the top level: ``from ragevalkit import RagevalError, JudgeError``.
"""
from ragevalkit.core.exceptions.answer_judge import JudgeError
from ragevalkit.core.exceptions.base import (
    ConfigError,
    InvalidInput,
    NotFoundError,
    RagevalError,
    TooLargeError,
)
from ragevalkit.core.exceptions.db_services import (
    ConflictError,
    GroupNotFound,
    StoreError,
    VersionNotFound,
)
from ragevalkit.core.exceptions.document_reader import DocumentError
from ragevalkit.core.exceptions.evaluation_runner import NoDatasetError, RunBusy, RunError
from ragevalkit.core.exceptions.spreadsheet_loader import DatasetError
from ragevalkit.core.exceptions.testcase_generator import GenerationBusy, GenerationError

__all__ = [
    "ConfigError", "ConflictError", "DatasetError", "DocumentError", "GenerationBusy", "GenerationError", "GroupNotFound",
    "InvalidInput", "JudgeError", "NoDatasetError", "NotFoundError", "RagevalError", "RunBusy", "RunError", "StoreError",
    "TooLargeError", "VersionNotFound",
]

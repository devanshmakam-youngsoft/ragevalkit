"""One place that turns errors into HTTP responses, so routes do not repeat try/except blocks.

Every error response has the same shape: ``{"detail": <plain-language message>, "code": <short name>}``.
"""
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ragevalkit.core.diagnostics import redact
from ragevalkit.core.exceptions.base import InvalidInput, NotFoundError, RagevalError, TooLargeError
from ragevalkit.core.exceptions.data_access import ConflictError
from ragevalkit.core.exceptions.document_reader import DocumentError
from ragevalkit.core.exceptions.evaluation_runner import NoDatasetError, RunBusy
from ragevalkit.core.exceptions.spreadsheet_loader import DatasetError
from ragevalkit.core.exceptions.testcase_generator import GenerationBusy

logger = logging.getLogger(__name__)

# (error type, HTTP status, short code), most specific first: the first match wins
HANDLED_ERRORS: list[tuple[type[BaseException], int, str]] = [
    (NotFoundError, 404, "not_found"),
    (TooLargeError, 413, "too_large"),
    (ConflictError, 409, "conflict"),
    (RunBusy, 409, "busy"),
    (GenerationBusy, 409, "busy"),
    (NoDatasetError, 400, "nothing_to_run"),
    (InvalidInput, 422, "invalid_input"),
    (DatasetError, 422, "invalid_file"),
    (DocumentError, 422, "invalid_file"),
]


def _describe(error: RagevalError) -> tuple[int, str]:
    for kind, status, code in HANDLED_ERRORS:
        if isinstance(error, kind):
            return status, code
    return 500, "error"


async def handle_library_error(request: Request, error: RagevalError) -> JSONResponse:
    """Turn a library error into a JSON response using its status and code from ``HANDLED_ERRORS``.

    An error type not listed there answers 500 ``"error"`` and is logged with its traceback.
    """
    status, code = _describe(error)
    if status >= 500:
        logger.error("%s %s failed: %s", request.method, request.url.path, error, exc_info=error)
    return JSONResponse({"detail": str(error), "code": code}, status_code=status)


async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """Anything nobody planned for: the traceback is logged, the person gets a plain message, a reference to quote,
    and the error's own text (secrets hidden) to show on request."""
    reference = uuid.uuid4().hex[:8]
    logger.error("[%s] %s %s failed unexpectedly", reference, request.method, request.url.path, exc_info=error)
    return JSONResponse(
        {"detail": f"Something went wrong on our side. Please try again; if it keeps happening, tell us reference {reference}.",
         "code": "server_error", "reference": reference, "technical": redact(f"{type(error).__name__}: {error}")},
        status_code=500,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Install the handlers for library errors and for unexpected exceptions on ``app``."""
    app.add_exception_handler(RagevalError, handle_library_error)
    app.add_exception_handler(Exception, handle_unexpected_error)

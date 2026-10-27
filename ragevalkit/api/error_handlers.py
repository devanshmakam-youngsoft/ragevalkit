"""One place that turns errors into HTTP responses, so routes do not repeat try/except blocks.

Every error response has the same shape: ``{"detail": <plain-language message>, "code": <short name>}``.
"""
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ragevalkit.datasets.exceptions import DatasetError
from ragevalkit.documents.exceptions import DocumentError
from ragevalkit.evaluation.exceptions import NoDatasetError, RunBusy
from ragevalkit.exceptions import InvalidInput, NotFoundError, RagevalError, TooLargeError
from ragevalkit.generation.exceptions import GenerationBusy
from ragevalkit.storage.exceptions import ConflictError

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
    status, code = _describe(error)
    if status >= 500:
        logger.error("%s %s failed: %s", request.method, request.url.path, error, exc_info=error)
    return JSONResponse({"detail": str(error), "code": code}, status_code=status)


async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """Anything nobody planned for: logged in full, answered with a reference the person can quote."""
    reference = uuid.uuid4().hex[:8]
    logger.error("[%s] %s %s failed unexpectedly", reference, request.method, request.url.path, exc_info=error)
    return JSONResponse(
        {"detail": f"Something went wrong on our side. Please try again; if it keeps happening, tell us reference {reference}.",
         "code": "server_error", "reference": reference},
        status_code=500,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RagevalError, handle_library_error)
    app.add_exception_handler(Exception, handle_unexpected_error)

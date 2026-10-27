"""Base exception types for ragevalkit.

Every library error inherits from ``RagevalError``, so callers can catch the base class to handle any ragevalkit
error, or a specific subclass for fine-grained handling. Each feature keeps its own errors in its own package:

    ragevalkit.exceptions              RagevalError, ConfigError, InvalidInput, NotFoundError, TooLargeError
    ragevalkit.datasets.exceptions     DatasetError
    ragevalkit.documents.exceptions    DocumentError
    ragevalkit.storage.exceptions      StoreError, VersionNotFound, ConflictError, GroupNotFound
    ragevalkit.evaluation.exceptions   RunError, RunBusy
    ragevalkit.generation.exceptions   GenerationError, GenerationBusy
    ragevalkit.judging.exceptions      JudgeError

All of them are also importable from the top level, which is the supported way:

    from ragevalkit import RagevalError, JudgeError, DatasetError
"""
import importlib


class RagevalError(Exception):
    """Base class for all ragevalkit exceptions."""


class ConfigError(RagevalError):
    """Invalid or conflicting value passed to serve() or Config."""


class InvalidInput(RagevalError, ValueError):
    """A value someone sent cannot be used; the message says why in plain words."""


class NotFoundError(RagevalError, KeyError):
    """Something that was asked for does not exist (or is no longer available)."""

    def __str__(self) -> str:
        return Exception.__str__(self)      # a KeyError would put quotes around the message


class TooLargeError(RagevalError):
    """An uploaded file is bigger than allowed."""


# Before the errors moved next to their features, all of them were imported from this module. This lookup keeps
# `from ragevalkit.exceptions import JudgeError` working. It has to be lazy: the feature modules import
# RagevalError from here, so importing them eagerly would be circular.
_MOVED = {
    "DatasetError": "ragevalkit.datasets.exceptions",
    "DocumentError": "ragevalkit.documents.exceptions",
    "StoreError": "ragevalkit.storage.exceptions",
    "VersionNotFound": "ragevalkit.storage.exceptions",
    "ConflictError": "ragevalkit.storage.exceptions",
    "GroupNotFound": "ragevalkit.storage.exceptions",
    "RunError": "ragevalkit.evaluation.exceptions",
    "RunBusy": "ragevalkit.evaluation.exceptions",
    "GenerationError": "ragevalkit.generation.exceptions",
    "GenerationBusy": "ragevalkit.generation.exceptions",
    "JudgeError": "ragevalkit.judging.exceptions",
}


def __getattr__(name: str):
    if name in _MOVED:
        return getattr(importlib.import_module(_MOVED[name]), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

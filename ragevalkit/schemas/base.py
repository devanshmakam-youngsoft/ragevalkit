"""The base of every response model."""
from pydantic import BaseModel, ConfigDict, model_serializer


class ApiResponse(BaseModel):
    """A response that says what it contains and still passes through anything else it was given.

    Only the fields that were actually returned are sent, so describing a response here never adds a key to it.
    """

    model_config = ConfigDict(extra="allow")

    @model_serializer(mode="wrap")
    def _only_what_was_returned(self, handler) -> dict:
        """Drop every field that nobody set, so the answer holds exactly the keys the route returned.

        Without this FastAPI fills each unset field with its default (``None``, ``[]``, ``0``), so a key
        that is missing from an older saved run would be sent as ``null`` and clients could no longer tell
        "absent" from "empty". Extra keys the route returned are kept as they are.
        """
        data = handler(self)
        given = self.model_fields_set | set(self.model_extra or {})
        return {key: value for key, value in data.items() if key in given}

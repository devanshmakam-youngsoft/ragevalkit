"""The base of every response model."""
from pydantic import BaseModel, ConfigDict, model_serializer


class ApiResponse(BaseModel):
    """A response that says what it contains and still passes through anything else it was given.

    Only the fields that were actually returned are sent, so describing a response here never adds a key to it.
    """

    model_config = ConfigDict(extra="allow")

    @model_serializer(mode="wrap")
    def _only_what_was_returned(self, handler):
        data = handler(self)
        given = self.model_fields_set | set(self.model_extra or {})
        return {key: value for key, value in data.items() if key in given}

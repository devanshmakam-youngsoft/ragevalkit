"""Request bodies for groups."""
from pydantic import BaseModel


class GroupName(BaseModel):
    """The name for a group that is being created or renamed."""

    name: str                       # must be unique among groups, ignoring capitals and surrounding spaces

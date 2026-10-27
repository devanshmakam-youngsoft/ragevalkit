"""Request bodies for groups."""
from pydantic import BaseModel


class GroupName(BaseModel):
    name: str

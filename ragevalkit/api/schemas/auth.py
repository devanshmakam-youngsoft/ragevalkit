"""Request bodies for signing in."""
from pydantic import BaseModel


class LoginBody(BaseModel):
    username: str
    password: str

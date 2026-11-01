"""Request bodies for signing in."""
from pydantic import BaseModel


class LoginBody(BaseModel):
    """The username and password sent to sign in."""

    username: str
    password: str                   # not checked when the server runs without login

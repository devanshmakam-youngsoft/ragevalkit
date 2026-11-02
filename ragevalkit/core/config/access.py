"""Who may open the dashboard."""
from ragevalkit.core.config.base import Settings
from ragevalkit.core.constants import SESSION_COOKIE_NAME


class AccessSettings(Settings):
    """Options for the dashboard login: the accepted users and how the session cookie is signed."""

    eval_users: str = "admin:admin123"           # comma-separated "name:password" pairs
    eval_secret: str = "dev-only-change-me"      # signs the session cookie; change it before exposing the server
    session_hours: int = 12                      # how long a sign-in stays valid
    session_cookie: str = SESSION_COOKIE_NAME
    require_login: bool = True                   # False: any username is accepted without a password

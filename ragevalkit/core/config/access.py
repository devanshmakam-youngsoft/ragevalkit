"""Who may open the dashboard."""
from ragevalkit.core.config.base import Settings
from ragevalkit.core.constants.library import SESSION_COOKIE_NAME


class AccessSettings(Settings):
    eval_users: str = "admin:admin123"
    eval_secret: str = "dev-only-change-me"
    session_hours: int = 12
    session_cookie: str = SESSION_COOKIE_NAME
    require_login: bool = True

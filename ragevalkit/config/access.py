"""Who may open the dashboard."""
from ragevalkit.config.base import Settings


class AccessSettings(Settings):
    eval_users: str = "admin:admin123"
    eval_secret: str = "dev-only-change-me"
    session_hours: int = 12
    session_cookie: str = "eval_session"
    require_login: bool = True

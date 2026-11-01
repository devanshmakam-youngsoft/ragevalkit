"""Reading a ``.env`` file so LiteLLM can find provider keys such as GROQ_API_KEY."""
import os
from pathlib import Path


def load_dotenv(path: str = ".env") -> None:
    """Load key=value pairs from a .env file into os.environ (does not overwrite existing vars)."""
    try:
        env_file = Path(path)
        if not env_file.exists():
            return
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass

from pathlib import Path

from fastapi.templating import Jinja2Templates

WEB_ROOT = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=str(WEB_ROOT / "templates"))

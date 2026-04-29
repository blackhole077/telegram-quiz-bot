from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.backends import make_backend
from core.config import settings
from core.service import QuizService

from .routers import exam, practice, quiz

_WEB_ROOT = Path(__file__).parent

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(_WEB_ROOT / "static")), name="static")
templates = Jinja2Templates(directory=str(_WEB_ROOT / "templates"))

_service = QuizService(make_backend(settings))


def _today() -> str:
    return date.today().isoformat()


app.include_router(quiz.router)
app.include_router(practice.router)
app.include_router(exam.router)


# NOTE: This will be our landing page where we'd select what we want to do (e.g., Quiz, Exam, etc.)
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    total, due = _service.get_stats(_today())
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"total": total, "due": due},
    )

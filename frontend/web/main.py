from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .dependencies import quiz_service
from .routers import exam, learn, practice, quiz

_WEB_ROOT = Path(__file__).parent

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(_WEB_ROOT / "static")), name="static")
templates = Jinja2Templates(directory=str(_WEB_ROOT / "templates"))


def _today() -> str:
    return date.today().isoformat()


app.include_router(quiz.router)
app.include_router(practice.router)
app.include_router(exam.router)
app.include_router(learn.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    total, due = quiz_service.get_stats(_today())
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"total": total, "due": due},
    )

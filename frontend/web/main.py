from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.config import settings
from .dependencies import quiz_service
from .logging_config import configure_logging
from .middleware import RequestLoggingMiddleware
from .routers import exam, learn, practice, quiz
from .session_store import session_store

_WEB_ROOT = Path(__file__).parent

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings)
    logger.info(
        "quiz-system starting",
        backend=settings.storage_type,
        model=settings.llm_model,
    )
    yield
    session_store.flush_all("quiz", quiz._states, 7200)
    session_store.flush_all("practice", practice._states, 7200)
    session_store.flush_all("exam", exam._states, 14400)
    session_store.flush_all("learn", learn._states, 3600)
    session_store.cleanup(datetime.utcnow())
    logger.info("quiz-system stopping")


app = FastAPI(lifespan=lifespan)
app.add_middleware(RequestLoggingMiddleware)
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


@app.get("/health")
async def health():
    checks = {}
    try:
        quiz_service._backend.load_questions()
        checks["backend"] = "ok"
    except Exception as exc:
        checks["backend"] = f"error: {type(exc).__name__}"

    checks["data_dir"] = "ok" if Path(settings.data_dir).exists() else "missing"

    status = "ok" if all(value == "ok" for value in checks.values()) else "degraded"
    return JSONResponse(
        {"status": status, "checks": checks},
        status_code=200 if status == "ok" else 503,
    )

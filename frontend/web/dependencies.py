"""Shared service instances for web routers."""

from backend.backends import make_backend
from core.config import settings
from core.service import QuizService

quiz_service = QuizService(make_backend(settings), settings.topics_path)

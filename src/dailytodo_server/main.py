"""ASGI application entry point."""

from fastapi import FastAPI

from .api import router
from .db import create_session_factory, ensure_database_schema
from .rate_limit import RateLimiter
from .settings import Settings, get_settings


def create_app(settings: Settings | None = None, create_tables: bool = False) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="DailyTodo Server", version="0.1.0")
    session_factory = create_session_factory(settings)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.auth_rate_limiter = RateLimiter(
        settings.auth_rate_limit_requests,
        settings.auth_rate_limit_window_seconds,
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)

    if create_tables:
        ensure_database_schema(session_factory.kw["bind"])

    return app


app = create_app()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import (
    ai,
    approvals,
    buyers,
    dashboard,
    finance,
    health,
    inbox,
    leads,
    marketing,
    me,
    public,
    tasks,
    webhooks,
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Real Estate Wholesaling Operating System API",
        version="0.1.0",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(ai.router)
    app.include_router(approvals.router)
    app.include_router(buyers.router)
    app.include_router(dashboard.router)
    app.include_router(finance.router)
    app.include_router(inbox.router)
    app.include_router(leads.router)
    app.include_router(marketing.router)
    app.include_router(me.router)
    app.include_router(public.router)
    app.include_router(tasks.router)
    app.include_router(webhooks.router)
    return app


app = create_app()

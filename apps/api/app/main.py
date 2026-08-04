from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.observability import initialize_error_monitoring
from app.routers import (
    ai,
    approvals,
    buyers,
    campaign_management,
    dashboard,
    deals,
    dispositions,
    email,
    esign_webhooks,
    field_operations,
    finance,
    health,
    help,
    inbox,
    integrations,
    lead_manager,
    leads,
    marketing,
    me,
    meta_webhooks,
    operating_model,
    operations,
    prospecting,
    public,
    resend_webhooks,
    tasks,
    transactions,
    underwriting,
    voice,
    webhooks,
)


def create_app() -> FastAPI:
    settings = get_settings()
    initialize_error_monitoring(settings, service_name="api")
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
    app.include_router(help.router)
    app.include_router(ai.router)
    app.include_router(approvals.router)
    app.include_router(buyers.router)
    app.include_router(campaign_management.router)
    app.include_router(dashboard.router)
    app.include_router(deals.router)
    app.include_router(dispositions.router)
    app.include_router(email.router)
    app.include_router(esign_webhooks.router)
    app.include_router(field_operations.router)
    app.include_router(finance.router)
    app.include_router(inbox.router)
    app.include_router(integrations.router)
    app.include_router(lead_manager.router)
    app.include_router(leads.router)
    app.include_router(marketing.router)
    app.include_router(meta_webhooks.router)
    app.include_router(me.router)
    app.include_router(operating_model.router)
    app.include_router(operations.router)
    app.include_router(prospecting.router)
    app.include_router(public.router)
    app.include_router(resend_webhooks.router)
    app.include_router(tasks.router)
    app.include_router(transactions.router)
    app.include_router(underwriting.router)
    app.include_router(voice.router)
    app.include_router(webhooks.router)
    return app


app = create_app()

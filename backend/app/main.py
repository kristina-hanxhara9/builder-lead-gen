"""FastAPI application entry point."""

import logging

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, dashboard, leads, letters, planning, qr
from app.api import settings as settings_api
from app.core.config import settings

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logging.basicConfig(level=logging.INFO if not settings.debug else logging.DEBUG)

app = FastAPI(
    title="Smith & Sons Lead Generation API",
    description="Automated lead generation from London planning applications",
    version="1.0.0",
)

# CORS — allow the configured frontend URL + localhost for local dev
_allowed_origins = [settings.frontend_url]
if settings.app_env == "development":
    _allowed_origins += ["http://localhost:3000", "http://localhost:3001"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Mount API routers
app.include_router(auth.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(leads.router, prefix="/api")
app.include_router(letters.router, prefix="/api")
app.include_router(planning.router, prefix="/api")
app.include_router(qr.router, prefix="/api")
app.include_router(settings_api.router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "builder-leads-api"}


@app.on_event("startup")
async def startup():
    logger = logging.getLogger(__name__)
    logger.info("Smith & Sons Lead Generation API starting...")
    if settings.secret_key.startswith("change-me"):
        logger.warning("SECRET_KEY is using the default value — set a secure key for production")
    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY not set — AI features will not work")


@app.on_event("shutdown")
async def shutdown():
    logging.getLogger(__name__).info("Shutting down...")

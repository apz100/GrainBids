from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routes.alerts import router as alerts_router
from app.api.routes.bids import router as bids_router
from app.api.routes.ingestion import router as ingestion_router
from app.api.routes.market_data import router as market_data_router
from app.api.routes.newsletter import router as newsletter_router
from app.api.routes.normalized_prices import router as normalized_prices_router
from app.api.routes.quotes import router as quotes_router
from app.api.routes.reference import router as reference_router
from app.api.routes.saved_searches import router as saved_searches_router
from app.api.routes.settings import router as settings_router
from app.api.routes.signals import router as signals_router
from app.api.routes.sources import router as sources_router
from app.api.routes.watchlists import router as watchlists_router
from app.core.config import settings
from app.db.session import get_engine


def create_app() -> FastAPI:
    app = FastAPI(
        title="GrainBids API",
        docs_url="/docs" if settings.api_enable_docs else None,
        redoc_url="/redoc" if settings.api_enable_docs else None,
        openapi_url="/openapi.json" if settings.api_enable_docs else None,
    )

    if settings.api_cors_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.api_cors_origins_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )

    @app.get("/health")
    def health():
        return {"ok": True, "env": settings.app_env}

    @app.get("/health/live")
    def health_live():
        return {"ok": True, "env": settings.app_env}

    @app.get("/health/ready")
    def health_ready():
        ok, details = _check_database()
        if ok:
            return {"ok": True, "env": settings.app_env, "database": details}
        return JSONResponse(status_code=503, content={"ok": False, "env": settings.app_env, "database": details})

    @app.get("/api/health/db")
    def db_health():
        ok, details = _check_database()
        if ok:
            return {"ok": True, "database": "connected", "env": settings.app_env}
        return JSONResponse(status_code=503, content={"ok": False, "database": "error", "error": details, "env": settings.app_env})

    app.include_router(reference_router)
    app.include_router(bids_router)
    app.include_router(sources_router)
    app.include_router(ingestion_router)
    app.include_router(market_data_router)
    app.include_router(newsletter_router)
    app.include_router(normalized_prices_router)
    app.include_router(alerts_router)
    app.include_router(quotes_router)
    app.include_router(watchlists_router)
    app.include_router(saved_searches_router)
    app.include_router(signals_router)
    app.include_router(settings_router)
    return app


app = create_app()


def _check_database() -> tuple[bool, str]:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        return True, "connected"
    except Exception as exc:
        return False, str(exc)


from fastapi import FastAPI
from sqlalchemy import text

from app.api.routes.alerts import router as alerts_router
from app.api.routes.bids import router as bids_router
from app.api.routes.ingestion import router as ingestion_router
from app.api.routes.market_data import router as market_data_router
from app.api.routes.normalized_prices import router as normalized_prices_router
from app.api.routes.quotes import router as quotes_router
from app.api.routes.reference import router as reference_router
from app.api.routes.settings import router as settings_router
from app.api.routes.signals import router as signals_router
from app.api.routes.sources import router as sources_router
from app.api.routes.watchlists import router as watchlists_router
from app.db.session import get_engine


def create_app() -> FastAPI:
    app = FastAPI(title="GrainBids API")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/api/health/db")
    def db_health():
        try:
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(text("select 1"))
            return {"ok": True, "database": "connected"}
        except Exception as exc:
            return {"ok": False, "database": "error", "error": str(exc)}

    app.include_router(reference_router)
    app.include_router(bids_router)
    app.include_router(sources_router)
    app.include_router(ingestion_router)
    app.include_router(market_data_router)
    app.include_router(normalized_prices_router)
    app.include_router(alerts_router)
    app.include_router(quotes_router)
    app.include_router(watchlists_router)
    app.include_router(signals_router)
    app.include_router(settings_router)
    return app


app = create_app()



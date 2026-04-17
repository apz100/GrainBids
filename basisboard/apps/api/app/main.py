from fastapi import FastAPI
from sqlalchemy import text

from app.api.routes.normalized_prices import router as normalized_prices_router
from app.api.routes.reference import router as reference_router
from app.api.routes.uploads import router as uploads_router
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
    app.include_router(uploads_router)
    app.include_router(normalized_prices_router)
    return app


app = create_app()


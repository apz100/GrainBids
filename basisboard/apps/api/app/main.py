from fastapi import FastAPI

from app.api.routes.uploads import router as uploads_router


def create_app() -> FastAPI:
    app = FastAPI(title="BasisBoard API")

    @app.get("/health")
    def health():
        return {"ok": True}

    app.include_router(uploads_router)
    return app


app = create_app()

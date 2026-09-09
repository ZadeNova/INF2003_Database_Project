"""FastAPI application entrypoint.

App object and health check only — routers are registered here once they exist.
"""

from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, debug=settings.debug)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe. Does not touch either database."""
    return {"status": "ok"}


# TODO: lifespan wiring for the Postgres pools and Motor client.
# TODO: app.include_router(...) per feature router.

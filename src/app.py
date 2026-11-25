"""The FastAPI application: one WebSocket endpoint per PBX."""

from fastapi import FastAPI
from loguru import logger

from config import Settings
from telephony import asterisk, freeswitch


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Reads the settings from the environment if none are given."""
    settings = settings or Settings.from_env()
    app = FastAPI(title="Voice agent", docs_url=None, redoc_url=None, openapi_url=None)

    app.include_router(asterisk.create_router(settings))
    backends = ["asterisk"]
    if settings.freeswitch:
        app.include_router(freeswitch.create_router(settings, settings.freeswitch))
        backends.append("freeswitch")
    else:
        logger.info("FREESWITCH_ESL_PASSWORD is not set: the FreeSWITCH endpoint is disabled")

    @app.get("/health")
    async def health():
        return {"status": "ok", "backends": backends}

    return app

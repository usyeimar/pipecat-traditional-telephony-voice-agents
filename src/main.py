"""Voice agent that answers phone calls from FreeSWITCH and Asterisk with Pipecat.

Run it with ``uv run src/main.py``.

Layout of this directory:

- ``config.py``   settings read from the environment
- ``agent/``      the conversation: speech services, tools and the pipeline (PBX-agnostic)
- ``telephony/``  one adapter per PBX: it accepts the PBX's WebSocket and hands a ``CallSession``
                  to the agent
- ``app.py``      the FastAPI application that mounts the adapters
"""

import sys

import uvicorn
from dotenv import load_dotenv
from loguru import logger

from app import create_app
from config import ConfigError, Settings


def main() -> None:
    # Docker Compose passes the environment itself; the .env file is for running on the host.
    load_dotenv()
    try:
        settings = Settings.from_env()
    except ConfigError as e:
        logger.error(e)
        sys.exit(1)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()

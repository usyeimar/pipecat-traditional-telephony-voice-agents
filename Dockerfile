# The Pipecat voice agent (src/).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies first: this layer is rebuilt only when they change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src ./src
COPY prompts ./prompts

RUN useradd --system --no-create-home agent
USER agent

EXPOSE 8765
CMD ["/app/.venv/bin/python", "src/main.py"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /app

RUN pip install --no-cache-dir "uv>=0.5"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY prompts ./prompts
COPY data ./data
COPY settings.yaml ./
RUN uv sync --frozen --no-dev && .venv/bin/python -m ask_my_cv.ingest

RUN useradd --system --no-create-home app && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK CMD .venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD [".venv/bin/uvicorn", "ask_my_cv.app:app", "--host", "0.0.0.0", "--port", "8000"]

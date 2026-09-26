FROM python:3.12-slim

COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0 /lambda-adapter /opt/extensions/lambda-adapter

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends locales \
 && sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
 && locale-gen \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "uv>=0.5"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY prompts ./prompts
COPY data ./data
COPY settings.yaml ./
COPY settings.aws.yaml ./
COPY models ./models
RUN uv sync --frozen --no-dev && .venv/bin/python -m ask_my_cv.ingest

RUN useradd --system --no-create-home app && chown -R app /app
ENV ASK_ENVIRONMENT=prod
# Lambda Web Adapter (ignoré hors Lambda) : l'extension relaie l'invocation vers uvicorn.
ENV AWS_LWA_PORT=8000 AWS_LWA_READINESS_CHECK_PATH=/healthz AWS_LWA_INVOKE_MODE=response_stream
USER app

EXPOSE 8000
HEALTHCHECK CMD .venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD [".venv/bin/uvicorn", "--factory", "ask_my_cv.app:create_app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers"]

FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

LABEL org.opencontainers.image.source=https://github.com/VoiD911/ask-my-cv

# Lambda Web Adapter tiré du miroir GHCR (mirror.yml) : même digest que
# public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0, donc mêmes octets.
COPY --from=ghcr.io/void911/aws-lambda-adapter:1.1.0@sha256:17cfd08eff1dfea3f6a9a1e9c65fdac80aa4919b6085e746615530f43f57d2f1 /lambda-adapter /opt/extensions/lambda-adapter
COPY --from=ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /app

# Correctifs de sécurité Debian appliqués sans attendre la reconstruction de l'image
# officielle (OpenSSL CVE-2026-75804 et CVE-2026-84782, corrigées en 3.5.7-1~deb13u3).
RUN apt-get update \
 && apt-get install -y --no-install-recommends locales \
 && apt-get install -y --no-install-recommends --only-upgrade openssl libssl3t64 openssl-provider-legacy \
 && sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
 && locale-gen \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY prompts ./prompts
COPY data ./data
COPY scripts/check_imports.py ./scripts/
COPY settings.yaml ./
COPY settings.aws.yaml ./
COPY models ./models
RUN uv sync --frozen --no-dev && .venv/bin/python -m ask_my_cv.ingest

RUN useradd --system --no-create-home app
ENV ASK_ENVIRONMENT=prod
# Lambda Web Adapter (ignoré hors Lambda) : l'extension relaie l'invocation vers uvicorn.
ENV AWS_LWA_PORT=8000 AWS_LWA_READINESS_CHECK_PATH=/healthz AWS_LWA_INVOKE_MODE=response_stream
USER app

EXPOSE 8000
HEALTHCHECK CMD .venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD [".venv/bin/uvicorn", "--factory", "ask_my_cv.app:create_app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers"]

FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project metadata and source needed for editable install
COPY pyproject.toml README.md ./
COPY law_ai ./law_ai
COPY manage.py ./

# Install Python dependencies (editable install requires law_ai/ + README.md
# to exist). BuildKit cache mount keeps pip's download/wheel cache across
# rebuilds: law_ai/ is COPYied above, so any code change invalidates this
# layer — the cache turns those reinstalls from a multi-GB download into a
# local re-link.
RUN --mount=type=cache,target=/root/.cache/pip pip install -e ".[dev,local-ai,future-auth]"

# BL-20260429-03: the optional NER pass (ENABLE_NER) needs a spaCy pipeline
# present in the image. Without it `ENABLE_NER=true` silently yields zero
# entities and the only documented cure is a host `pip install`, which the
# Docker-first rule forbids. Kept as its own `--no-deps` layer so the
# resolution above is neither re-run nor perturbed — the wheel is the whole
# `nlp` extra, and spaCy itself is already a core dependency.
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-deps \
    "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"

# Copy the rest of the application code (tests, scripts, etc.)
COPY . .

# Expose port
EXPOSE 8000

# Healthcheck (compose overrides this with its own gated check; the
# start-period covers the collectstatic+migrate+checkpointer boot chain
# for standalone `docker run` use).
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Spec 011: Django ASGI via daphne. Migrations + checkpointer schema run
# at container start so the dev stack is self-bootstrapping.
CMD ["sh", "-c", "python manage.py collectstatic --noinput && python manage.py migrate --noinput && python manage.py ensure_checkpointer && daphne -b 0.0.0.0 -p 8000 law_ai.asgi:application"]
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project metadata and source needed for editable install
COPY pyproject.toml README.md ./
COPY lexgraph ./lexgraph
COPY manage.py ./

# Install Python dependencies (editable install requires lexgraph/ + README.md to exist)
RUN pip install --no-cache-dir -e ".[dev,local-ai]"

# Copy the rest of the application code (tests, scripts, etc.)
COPY . .

# Expose port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Spec 011: Django ASGI via daphne. Migrations + checkpointer schema run
# at container start so the dev stack is self-bootstrapping.
CMD ["sh", "-c", "python manage.py collectstatic --noinput && python manage.py migrate --noinput && python manage.py ensure_checkpointer && daphne -b 0.0.0.0 -p 8000 lexgraph.asgi:application"]
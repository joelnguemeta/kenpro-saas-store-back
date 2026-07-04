# syntax=docker/dockerfile:1
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/usr/local

# uv gère l'installation des dépendances
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Installe les dépendances (couche mise en cache tant que les lockfiles ne changent pas)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# gunicorn pour servir l'app (pas listé dans pyproject)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system gunicorn

COPY . .

EXPOSE 8000

CMD ["gunicorn", "kenpro_store.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
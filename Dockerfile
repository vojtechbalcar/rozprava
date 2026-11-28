# Rozprava in production (docs/production-deployment.md): one image for the web app
# and the daily import job. Cloudflare Containers run linux/amd64 images.
FROM python:3.14-slim-trixie

# pip rather than COPY --from the uv image, which the classic builder cannot export.
RUN pip install --no-cache-dir uv==0.13.7

# Python 3.14 has Linux wheels for every dependency, including ufal.morphodita, so
# nothing is compiled. LANG matters: Czech text and PostgreSQL expect UTF-8.
ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    ROZPRAVA_DATA_DIR=/data \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
COPY scripts/fetch_morphology.py ./scripts/
# The Czech tagger (26 MB, CC BY-NC-SA) is baked in; only the import job loads it.
RUN uv sync --frozen --no-dev && python scripts/fetch_morphology.py

RUN useradd --system --uid 10001 --home-dir /data rozprava \
    && mkdir -p /data/log /data/cache \
    && chown -R rozprava /data/log /data/cache
USER rozprava

EXPOSE 8080
# The Worker in front terminates HTTPS and forwards the visitor's address.
CMD ["uvicorn", "rozprava.main:app", "--host", "0.0.0.0", "--port", "8080", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]

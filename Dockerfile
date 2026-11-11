# The backend (Python API) as a container, for Railway or any Docker host.
# The website in web/ is deployed separately. Keys come from the host's settings (environment
# variables), never from this file or the image: see "Deploy to Railway" in the README.

FROM python:3.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    JOBCV_TESSERACT_CMD=tesseract \
    JOBCV_TESSDATA_DIR=/app/tessdata \
    JOBCV_DATA_DIR=/data

WORKDIR /app

# OCR for scanned CVs
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# English and Arabic OCR models: the same tessdata_best files the tests use, checked by hash so
# a changed or tampered download stops the build.
RUN mkdir -p /app/tessdata && cd /app/tessdata \
 && curl -fsSL -o eng.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata \
 && curl -fsSL -o ara.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/ara.traineddata \
 && printf '%s  %s\n' \
      8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba eng.traineddata \
      ab9d157d8e38ca00e7e39c7d5363a5239e053f5b0dbdb3167dde9d8124335896 ara.traineddata \
    | sha256sum -c -

# Python libraries, exactly as locked (no test tools)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
# README.md: pyproject.toml names it as the package description, so the install needs it
COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# Chromium for the PDFs, with the system libraries it needs
RUN uv run --no-sync playwright install --with-deps chromium

# One process only: runs, the allowance and the retention sweep live in this process and its
# SQLite files. "::" listens on IPv6 and IPv4, which Railway's private network needs.
EXPOSE 8000
CMD ["sh", "-c", "exec uv run --no-sync fastapi run --host :: --port ${PORT:-8000} --workers 1"]

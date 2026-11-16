# Multi-stage production build for SummaryBot
FROM debian:bookworm-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    PATH="/app/.venv/bin:$PATH"

# Install runtime dependencies: ffmpeg, libmagic1, ca-certificates, curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libmagic1 \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv from official binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Create unprivileged apps user (UID 1000)
RUN groupadd -g 1000 apps && useradd -u 1000 -g apps -m -s /bin/bash apps

WORKDIR /app

# Prepare python directory
RUN mkdir -p /opt/uv/python

# Copy dependency specifications first for layer caching
COPY pyproject.toml uv.lock README.md ./

# Install production dependencies (without project itself yet)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source code
COPY src ./src

# Install summary-bot project into virtualenv
RUN uv sync --frozen --no-dev

# Set ownership
RUN chown -R apps:apps /app /opt/uv

USER apps

ENTRYPOINT ["summary-bot", "tg-serve"]

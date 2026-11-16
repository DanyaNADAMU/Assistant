# Multi-stage production build for SummaryBot
FROM debian:bookworm-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

# Install runtime dependencies: ffmpeg, libmagic1, ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libmagic1 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv from official binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Create unprivileged apps user (UID 1000)
RUN groupadd -g 1000 apps && useradd -u 1000 -g apps -m -s /bin/bash apps

WORKDIR /app

# Copy dependency specifications first for layer caching
COPY pyproject.toml uv.lock ./

# Install production dependencies
RUN uv sync --frozen --no-dev

# Copy application source code
COPY src ./src
COPY README.md ./

# Re-sync to install the summary-bot package itself
RUN uv sync --frozen --no-dev

# Set ownership
RUN chown -R apps:apps /app

USER apps

ENTRYPOINT ["uv", "run", "summary-bot", "tg-serve"]

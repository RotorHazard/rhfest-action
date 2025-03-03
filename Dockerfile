FROM ghcr.io/astral-sh/uv:python3.13-alpine
ENV UV_LINK_MODE=copy

# Set the working directory
WORKDIR /app

# Copy project metadata files
COPY pyproject.toml uv.lock ./

# Install dependencies first (before copying source code for caching efficiency)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy RHFest source code
COPY rhfest /app/rhfest

# Install the project itself (so it's recognized as an installed package)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Ensure Python can find installed binaries & packages
ENV PATH="/app/.venv/bin:$PATH"

# Reset the entrypoint, don't invoke `uv`
ENTRYPOINT []

# Run RHFest validation
CMD ["python", "/app/rhfest/core.py"]

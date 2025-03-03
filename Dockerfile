FROM ghcr.io/astral-sh/uv:python3.13-alpine

# Set the working directory
WORKDIR /app

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Copy the source code
COPY rhfest /app/rhfest

# Run the container
CMD ["uv", "run", "python", "/app/rhfest/core.py"]

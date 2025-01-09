# Basisimage met Python
FROM python:3.13-slim

# Installeer UV (dependency manager)
RUN pip install uv

# Stel werkdirectory voor scripts in
WORKDIR /app

# Kopieer alle bestanden van `rhfest-actions` naar `/rhfest`
COPY . .

# Installeer dependencies via UV
RUN uv sync --no-group dev

# Stel werkdirectory voor GitHub Actions mount in
ENV WORKSPACE=/github/workspace

# Debug de mappenstructuur bij runtime
ENTRYPOINT ["sh", "-c", "ls -la /github/workspace && uv run python /app/rhfest/core.py $WORKSPACE"]
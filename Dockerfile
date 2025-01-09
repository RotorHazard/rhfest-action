FROM python:3.13-slim
LABEL Maintainer="Klaas Schoute"

RUN pip install uv

WORKDIR /app

COPY . ./app

RUN uv sync --no-group dev

ENTRYPOINT [ "uv", "run", "python", "rhfest/core.py" ]

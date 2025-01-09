FROM python:3.13-slim
LABEL Maintainer="Klaas Schoute"

RUN pip install uv

COPY . .

RUN uv sync --no-group dev

ENTRYPOINT [ "uv", "run", "python", "rhfest/core.py" ]

FROM python:3.13-slim

# Set the working directory
WORKDIR /app

# C
COPY . .

# Install dependencies
RUN pip install voluptuous

# Set the environment variable
ENV WORKSPACE=/github/workspace

# Run the container
ENTRYPOINT ["python", "/app/rhfest/core.py", "$WORKSPACE"]

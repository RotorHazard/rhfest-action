FROM python:3.13-slim

# Set the working directory
WORKDIR /app

# Copy the source code
COPY rhfest ./rhfest

# Install dependencies
RUN pip install voluptuous requests

# Run the container
ENTRYPOINT ["python", "/app/rhfest/core.py"]

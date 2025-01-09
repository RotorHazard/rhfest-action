# Basisimage met Python
FROM python:3.13-slim

# Stel werkdirectory voor scripts in
WORKDIR /app

# Kopieer alle bestanden van `rhfest-actions` naar `/rhfest`
COPY . .

# Installeer dependencies via UV
RUN pip install voluptuous

# Stel werkdirectory voor GitHub Actions mount in
ENV WORKSPACE=/github/workspace

# Debug de mappenstructuur bij runtime
ENTRYPOINT ["sh", "-c", "ls -la /github/workspace && python /app/rhfest/core.py $WORKSPACE"]
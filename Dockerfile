FROM python:3.12-slim

WORKDIR /app

# Install system dependencies required by geopandas/osmnx
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Generate Prisma client
COPY schema.prisma .
RUN prisma generate

COPY . .

EXPOSE 5000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "5000"]

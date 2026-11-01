# ===========================================================================
# Stage 1: Build React Frontend
# ===========================================================================
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

# Copy package descriptors first for Docker layer caching
COPY frontend/package*.json ./
RUN npm ci

# Copy full frontend source and build static distribution
COPY frontend/ ./
RUN npm run build

# ===========================================================================
# Stage 2: Production Python Backend Container
# ===========================================================================
FROM python:3.11-slim

# Avoid writing .pyc files and buffer stdout/stderr for responsive logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    CACHE_DIR=/tmp/.cache

WORKDIR /app

# Install minimal OS dependencies for wheel builds, shared libraries, and healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libexpat1 \
    binutils \
    && rm -rf /var/lib/apt/lists/*

# Add explicit verification of libexpat1 shared library presence and registration
RUN ldconfig && \
    dpkg -L libexpat1 | grep 'libexpat.so.1' && \
    ldconfig -p | grep libexpat

# Install Python requirements
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Add diagnostic verification of rasterio and shared library linkage
RUN python -c "import rasterio; print('Rasterio successfully loaded from:', rasterio.__file__)" && \
    python -c "import rasterio; import glob, subprocess; so_files = glob.glob(rasterio.__path__[0] + '/**/*.so', recursive=True); [subprocess.run(['ldd', s], check=True) for s in so_files[:3]]"

# Copy application source code
COPY core/ ./core/
COPY api/ ./api/
COPY docs/ ./docs/

# Verify API and core application can be loaded
RUN python -c "from api.main import app; print('EmberRoute FastAPI application successfully loaded')"

# Copy built frontend static distribution from Stage 1 into frontend/dist
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create dedicated non-root user (UID 1000 standard for Hugging Face Spaces)
RUN useradd -m -u 1000 user && \
    mkdir -p /tmp/.cache && \
    chown -R user:user /app /tmp/.cache

USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

EXPOSE 7860

# Docker healthcheck querying /api/health
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:7860/api/health || exit 1

# Start FastAPI application with single worker
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]

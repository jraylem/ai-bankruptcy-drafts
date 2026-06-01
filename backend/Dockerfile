# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    postgresql-client \
    ca-certificates \
    wget \
    gnupg \
    libnss3 \
    libatk-bridge2.0-0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxcb1 \
    libxrandr2 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libpango-1.0-0 \
    libasound2 \
    libatspi2.0-0 \
    libxshmfence1 \
    fonts-liberation \
    fonts-unifont \
    fonts-freefont-ttf \
    libreoffice \
    libreoffice-writer \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install uv (Python package manager)
RUN pip install uv

# Install Python dependencies
RUN uv sync --frozen

# Copy source code
COPY src/ ./src/

# Copy migrations directory
COPY migrations/ ./migrations/

# Copy bankruptcy knowledge files
COPY bankruptcy_knowledge/ ./bankruptcy_knowledge/

# Copy wait script
COPY wait-for-it.sh ./wait-for-it.sh
RUN chmod +x ./wait-for-it.sh

# Create uploads directory
RUN mkdir -p uploads

# Expose port
EXPOSE 8000

# Set environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Run the application. Multi-worker for production (Railway): a single
# stalled request can no longer take down the whole API. docker-compose
# overrides this CMD with --reload + single worker for local dev.
CMD ["./wait-for-it.sh", "uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for git
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ src/
COPY pyproject.toml .

# Install the package (non-editable for production)
RUN pip install --no-cache-dir .

# Verify installation
RUN miie --version

# Create non-root user
RUN useradd -m -r -s /bin/false miie && \
    chown -R miie:miie /app
USER miie

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD miie status || exit 1

ENTRYPOINT ["miie"]
CMD ["--help"]

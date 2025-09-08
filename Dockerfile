FROM debian:bookworm 

RUN apt update && apt upgrade -y
RUN apt install -y gcc

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv sync --frozen --no-cache

# Copy source code
COPY github_stats/ ./github_stats/

# Create directories for data persistence
RUN mkdir -p /app/downloaded-events /app/state

# Expose FastAPI port
EXPOSE 8000

# Set environment variables
ENV PYTHONPATH=/app
ENV UV_SYSTEM_PYTHON=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD uv run python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run the application
CMD ["uv", "run", "-m", "github_stats"]

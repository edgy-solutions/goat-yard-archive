# Modern Backend Dockerfile using astral-sh/uv
FROM python:3.12-slim

# Install uv into the system
COPY --from=ghcr.io/astral-sh/uv:0.4.15 /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy project definition and lock file first for caching
COPY pyproject.toml uv.lock /app/

# Install the backend dependencies
RUN uv sync --extra backend --no-dev

# Copy the rest of the source
COPY . /app/

# Set Run Command using our script but adjusting for uv
RUN chmod +x .s2i/bin/run

EXPOSE 8000

# S2I override - use script or direct command
CMD [".s2i/bin/run"]

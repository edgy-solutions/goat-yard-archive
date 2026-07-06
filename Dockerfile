# Modern Backend Dockerfile using astral-sh/uv
FROM python:3.12-slim

# Commit SHA baked in at build time and exposed as an env var. The API
# attaches it to each Langfuse trace's metadata so the daily Zone-3 judge
# report can name which build generated the traffic it's judging.
# Permanent protection against the prod-was-stale trap: a stale build
# announces itself in every daily Slack post.
ARG COMMIT_SHA=unknown
ENV COMMIT_SHA=${COMMIT_SHA}

# Install uv into the system
COPY --from=ghcr.io/astral-sh/uv:0.4.15 /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy project definition and lock file first for caching
COPY pyproject.toml uv.lock /app/

# Install the backend dependencies (ignore building the project package)
RUN uv sync --extra backend --no-dev --no-install-project

# Copy the rest of the source
COPY . /app/

# Set Run Command using our script but adjusting for uv
RUN chmod +x .s2i/bin/run

EXPOSE 8000

# S2I override - use script or direct command
CMD [".s2i/bin/run"]

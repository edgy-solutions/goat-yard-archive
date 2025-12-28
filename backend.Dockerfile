# Backend Dockerfile using S2I logic
FROM registry.access.redhat.com/ubi9/python-312

# 1. Copy application source
# Switch to root to ensure we can write/mod files
USER root
COPY . /tmp/src

# 2. Assemble (Install dependencies)
# We use the standard S2I assemble script which handles PIP/Venv.
# It uses our requirements.txt automatically.
# Fix: Use absolute path since WORKDIR usually differs from /tmp/src
RUN chmod +x /tmp/src/.s2i/bin/*
RUN /usr/libexec/s2i/assemble

# 3. Set Run Command
# Copy our custom run script to the S2I bin directory to override default behavior
COPY .s2i/bin/run /usr/libexec/s2i/run
RUN chmod +x /usr/libexec/s2i/run

USER 1001
CMD /usr/libexec/s2i/run

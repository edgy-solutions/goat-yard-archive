# Backend Dockerfile using S2I logic
FROM registry.access.redhat.com/ubi8/python-39

# 1. Copy application source
COPY . /tmp/src

# 2. Assemble (Install dependencies)
# We use the standard S2I assemble script which handles PIP/Venv.
# It uses our requirements.txt automatically.
RUN chmod +x .s2i/bin/*
RUN /usr/libexec/s2i/assemble

# 3. Set Run Command
# This will invoke our custom .s2i/bin/run script if present, or we can call it directly.
CMD /usr/libexec/s2i/run

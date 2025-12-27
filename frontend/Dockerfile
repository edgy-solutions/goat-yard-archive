# Frontend Dockerfile using S2I logic
FROM registry.access.redhat.com/ubi8/nodejs-18

# 1. Copy application source
# Switch to root to ensure we can write/mod files
USER root
COPY . /tmp/src

# 2. Assemble (Install deps & Build)
# Our custom assemble script handles npm install & build
# The builder looks for .s2i/bin/assemble in /tmp/src
# BUT we removed custom assemble to use image native assemble which is cleaner
# We must ensure permissions for scripts
RUN chmod +x /tmp/src/.s2i/bin/*
RUN /usr/libexec/s2i/assemble

# 3. Set Run Command
# Uses our custom .s2i/bin/run script (which runs 'npx serve')
CMD /usr/libexec/s2i/run

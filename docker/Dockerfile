# Sandbox container for executing agent-generated skills
#
# Build: docker build -t nethack-skill-sandbox docker/
# Test:  docker run --rm nethack-skill-sandbox python -c "print('ok')"

FROM python:3.10-slim

# Install uv for fast package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install minimal dependencies (no NLE - API calls go through proxy)
RUN uv pip install --system --no-cache \
    numpy \
    && rm -rf /root/.cache

# Create non-root user for security
RUN useradd -m -s /bin/bash sandbox

# Copy the skill runner script
COPY run_skill.py /home/sandbox/run_skill.py
COPY api_stub.py /home/sandbox/api_stub.py

# Set working directory
WORKDIR /sandbox

# Run as non-root user
USER sandbox

# Default command runs the skill runner
ENTRYPOINT ["python", "-u", "/home/sandbox/run_skill.py"]

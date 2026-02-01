# blog-toolkit with agent-browser for full Substack crawling
# Use in GitHub Actions or locally: docker build -t blog-toolkit .

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install Node.js and agent-browser dependencies (Chromium needs system libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" >> /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install agent-browser and Chromium (for Substack JS rendering)
RUN npm install -g agent-browser \
    && agent-browser install --with-deps \
    && rm -rf /root/.npm

# Copy project
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Install blog-toolkit
ENV UV_NO_DEV=1
RUN uv sync --frozen --no-dev

# Default: run blog-toolkit
ENTRYPOINT ["uv", "run", "blog-toolkit"]
CMD ["--help"]

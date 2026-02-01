# blog-toolkit - RSS, sitemap, and web crawler for blog collection
# Substack: uses sitemap for full archive (no browser needed)

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

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

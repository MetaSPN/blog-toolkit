# Docker and GitHub Actions

Run blog-toolkit in Docker or GitHub Actions. Substack: uses sitemap for full archive (300+ posts, no browser needed).

## Published Image (GHCR)

The image is published to GitHub Container Registry. Use it in other projects without building:

```bash
# Pull and run (no build required)
docker pull ghcr.io/OWNER/blog-toolkit:latest
docker run --rm -i --ipc=host \
  -v $(pwd)/output:/out \
  ghcr.io/OWNER/blog-toolkit:latest \
  pull https://example.substack.com/ -o /out/posts.json
```

Replace `OWNER` with the GitHub org or username (e.g. `leoguinan`). Tags: `latest` (main branch), `main`, and version tags on releases.

**Making the package public:** GHCR packages are private by default. To allow unauthenticated pulls: repo → Packages → blog-toolkit → Package settings → Change visibility → Public.

### Publish workflow: `.github/workflows/publish-docker.yml`

Builds and pushes the image to `ghcr.io/OWNER/blog-toolkit` on:
- Push to `main` (when Dockerfile, src, or pyproject changes)
- Release published (creates version tags)
- Manual trigger

---

## Docker

### Build locally

```bash
docker build -t blog-toolkit .
```

### Run locally

```bash
# Pull a single feed
docker run --rm -i --ipc=host \
  -v $(pwd)/output:/out \
  blog-toolkit pull https://michaelgarfield.substack.com/ -o /out/posts.json

# With multiple feeds
for url in https://example1.substack.com/ https://example2.substack.com/; do
  name=$(echo "$url" | sed 's|https://||;s|[^a-z0-9]|-|g' | cut -c1-30)
  docker run --rm -i --ipc=host \
    -v $(pwd)/output:/out \
    blog-toolkit pull "$url" -o "/out/${name}.json"
done
```

**Flags:**
- `--ipc=host` — Recommended for Chromium (avoids memory issues)
- `-v $(pwd)/output:/out` — Mount output directory into container

### What's included

- Python 3.12 + uv
- blog-toolkit (RSS, sitemap, web crawler)

---

## GitHub Actions

### Workflow: `.github/workflows/pull-feeds.yml`

Automated feed pulling using the Docker image.

**Triggers:**
- **Manual**: Actions → Pull Feeds → Run workflow (optional: comma-separated blog URLs)
- **Schedule**: Daily at 06:00 UTC
- **Push**: When workflow or `feeds.txt` changes on `main`

### Configuring feeds

**Option 1: `feeds.txt` (recommended)**

Create `feeds.txt` in the repo root, one URL per line:

```
https://michaelgarfield.substack.com/
https://another.substack.com/
```

**Option 2: Workflow dispatch input**

When running manually, paste comma-separated URLs in the "feeds" input.

**Option 3: Default**

If neither is set, pulls `https://michaelgarfield.substack.com/`.

### Output

- JSON files are written to `output/` and uploaded as artifacts
- Artifacts: Actions → Run → Artifacts → `feed-outputs`
- Retention: 30 days

### Build time

First run builds the Docker image (~5–10 min). Subsequent runs use GHA cache for faster builds (~1–2 min).

---

## Requirements

| Environment | Notes |
|-------------|-------|
| **Local Docker** | Docker with enough memory for Chromium (~2GB recommended) |
| **GitHub Actions** | `ubuntu-latest` runner (includes Docker) |
| **Substack** | RSS + sitemap (300+ posts, no browser) |
| **Other blogs** | RSS or static HTML crawl |

---

## Troubleshooting

### Chromium crashes / out of memory

- Ensure `--ipc=host` when running Docker
- For GHA, the default runner should be sufficient; if timeouts occur, increase `timeout-minutes`

### Slow Substack crawl

- Sitemap fetches each post page; at 1s delay, 200 posts ≈ 3–4 minutes

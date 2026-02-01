# Docker and GitHub Actions

Run blog-toolkit with agent-browser in Docker or GitHub Actions for full Substack crawling (beyond the ~20-post RSS limit).

## Docker

### Build

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
- blog-toolkit (RSS + crawler)
- Node.js + agent-browser + Chromium (for Substack JS rendering)
- System dependencies for Chromium on Linux

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
| **Substack** | agent-browser required for full archive (RSS returns ~20 posts only) |
| **Other blogs** | RSS-only works without agent-browser |

---

## Troubleshooting

### Chromium crashes / out of memory

- Ensure `--ipc=host` when running Docker
- For GHA, the default runner should be sufficient; if timeouts occur, increase `timeout-minutes`

### agent-browser not found

- Verify the Docker image built correctly: `docker run --rm blog-toolkit which agent-browser`
- The image includes `agent-browser install --with-deps` during build

### Slow Substack crawl

- Substack archive uses infinite scroll; the crawler scrolls 15+ times with 3s delays
- Expect 1–3 minutes per Substack blog depending on post count

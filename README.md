# Blog Toolkit

A comprehensive Python toolkit for collecting, storing, and analyzing multiple blogs with RSS feed and web crawler support.

## Features

- **Multiple Collection Methods**: Automatically detect and use RSS feeds, or fall back to web crawling
- **Comprehensive Analysis**: Temporal patterns, content metrics, topic analysis, and sentiment analysis
- **Cross-Blog Comparison**: Compare metrics across blogs by the same author or different authors
- **CLI Interface**: Full-featured command-line interface for all operations
- **Web Dashboard**: Interactive web interface with charts and visualizations
- **SQLite Storage**: Local database for storing all blog data and metadata

## Installation

This project uses [UV](https://github.com/astral-sh/uv) for package management.

```bash
# Install UV if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup the project
cd blog-toolkit
uv sync
```

## Quick Pull (One-Off, No Install)

Pull blog posts from any URL directly to a file—no database or setup:

```bash
uvx blog-toolkit pull https://example.substack.com -o ./posts.json
```

Requires [uv](https://github.com/astral-sh/uv). Output formats: `--format json` (default) or `--format csv`. Specify `-o` for output file or directory.

## Quick Start

### Using the CLI

```bash
# Add a blog (auto-detects RSS or uses crawler)
uv run blog-toolkit add https://example.com/blog

# Add a blog with specific method
uv run blog-toolkit add https://example.com/blog --method rss

# List all blogs
uv run blog-toolkit list

# Update a blog (collect new posts)
uv run blog-toolkit update --blog-id 1

# Update all blogs
uv run blog-toolkit update --all

# Analyze a blog
uv run blog-toolkit analyze --blog-id 1

# Analyze all blogs by an author
uv run blog-toolkit analyze --author "John Doe"

# Compare two blogs
uv run blog-toolkit compare 1 2

# Export data
uv run blog-toolkit export --format json --output data.json
```

### Using the Web Dashboard

```bash
# Start the web server
uv run python -m blog_toolkit.web.app

# Or use the Flask CLI
uv run flask --app blog_toolkit.web.app run
```

Then open your browser to `http://127.0.0.1:5000`

## Project Structure

```
blog-toolkit/
├── src/
│   └── blog_toolkit/
│       ├── config.py       # Configuration management
│       ├── database.py     # SQLite database models
│       ├── feeds.py        # RSS/Atom feed parser
│       ├── crawler.py      # Web crawler
│       ├── collector.py    # Unified collection interface
│       ├── analyzer.py     # Analysis engine
│       ├── cli.py          # CLI interface
│       └── web/            # Web dashboard
│           ├── app.py      # Flask application
│           └── templates/  # HTML templates
├── tests/                  # Test files
├── data/                   # Database storage (gitignored)
└── pyproject.toml          # Project configuration
```

## Configuration

Copy `.env.example` to `.env` and customize settings:

```bash
cp .env.example .env
```

Key settings:
- `BLOG_TOOLKIT_DB`: Database file path (default: `data/blogs.db`)
- `CRAWLER_MAX_DEPTH`: Maximum crawl depth (default: 10)
- `REQUEST_TIMEOUT`: HTTP request timeout in seconds (default: 30)
- `WEB_PORT`: Web dashboard port (default: 5000)

## Analysis Features

### Temporal Analysis
- Posting frequency (daily/weekly/monthly)
- Posting patterns (time of day, day of week)
- Gaps between posts
- Date range analysis

### Content Analysis
- Word count distribution and trends
- Reading time calculations
- Content length over time

### Topic Analysis
- Keyword extraction
- Tag and category distribution
- Top keywords identification

### Sentiment Analysis
- Overall sentiment (positive/neutral/negative)
- Per-post sentiment scores
- Sentiment trends over time

## Database Schema

- **blogs**: Blog metadata (name, URL, feed URL, author, collection method)
- **posts**: Individual blog posts (title, content, metadata, word count, etc.)
- **analyses**: Cached analysis results for performance

## CLI Commands

- `add <url>` - Add a new blog
- `update [--blog-id <id>] [--all]` - Update blog(s)
- `analyze [--blog-id <id>] [--author <name>]` - Run analysis
- `list` - List all blogs
- `show <blog-id>` - Show blog details
- `compare <blog-id1> <blog-id2>` - Compare two blogs
- `export [--format json|csv] [--output <file>]` - Export data

## Web Dashboard Features

- **Dashboard**: Overview of all blogs, recent posts, statistics
- **Blog Detail**: Individual blog view with posts, metrics, and charts
- **Author View**: Aggregate view of all blogs by an author
- **Comparison View**: Side-by-side comparison of blogs
- **Interactive Charts**: Plotly charts for trends and metrics

## Documentation

- **[Feed Extraction Workarounds](docs/FEED_EXTRACTION_WORKAROUNDS.md)** — Mechanisms for pulling RSS feed data from Substack and other platforms (platform limits, JS rendering, feed discovery, content parsing). Shareable guide for developers building similar tools.
- **[Docker and GitHub Actions](docs/DOCKER_AND_CI.md)** — Run blog-toolkit with agent-browser in Docker or GitHub Actions for full Substack crawling (beyond the ~20-post RSS limit).

## Development

```bash
# Install development dependencies
uv sync --dev

# Run tests
uv run pytest

# Format code
uv run black src/

# Type checking
uv run mypy src/
```

## License

MIT

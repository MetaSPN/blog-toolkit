# RSS Feed Data Extraction Workarounds

A developer guide documenting mechanisms for pulling RSS feed data from Substack and other platforms. Based on lessons learned building [blog-toolkit](https://github.com/leoguinan/blog-toolkit).

---

## Executive Summary

RSS feeds are the obvious choice for collecting blog content—until they fail. Many platforms impose hard limits, use JavaScript rendering that breaks naive scrapers, or expose feeds in inconsistent formats. This document captures what we learned and what actually works.

### Common Pitfalls

- **Platform limits**: Substack (~20 posts), Ghost (~15 posts) cap RSS output
- **JavaScript rendering**: List pages may render content client-side; `requests` + BeautifulSoup returns incomplete HTML
- **Inconsistent formats**: Content in `content`, `summary`, or `description`; dates as tuples or strings
- **No pagination**: Most feeds do not support paginated access; you cannot "page through" to get older posts

### What Works

1. Use RSS first when available—it's fast and reliable for recent posts
2. Supplement with crawler when RSS is limited (platform-specific strategies)
3. For Substack, use sitemap to bypass RSS limits (no browser needed)
4. Probe feed discovery heuristics; validate with Content-Type checks
5. Normalize content and dates across feed formats

---

## Substack-Specific Workarounds

Substack RSS is limited to ~20 posts. Use the sitemap to get the full archive.

### RSS Feed Limitations

- **Substack RSS feeds return only ~20 most recent posts** (hard limit)
- Cannot be circumvented via feed pagination—Substack does not support it
- Feed URL is typically `{blog}.substack.com/feed`

**Strategy**: Use RSS for the first 20 posts (with full content), then supplement via sitemap for the rest.

### Sitemap (Primary Method)

Substack exposes `sitemap.xml` with hundreds of post URLs—no browser needed.

- **URL**: `{blog}.substack.com/sitemap.xml`
- **Parse**: Extract `<loc>` tags with regex; filter for `/p/` and blog domain
- **Content**: Fetch each post page (server-rendered); extract title, date, article body
- **Use**: `--method sitemap` or collector auto-supplements when Substack detected

Post URL pattern: `{blog}.substack.com/p/{slug}`

---

## Feed Discovery Workarounds

When given a blog URL, you need to discover the feed URL. Probe in this order.

### HTML Link Patterns

Parse the blog's HTML and look for these `<link>` tags (in order of specificity):

| Pattern | Example |
|---------|---------|
| `type="application/rss+xml"` | `<link type="application/rss+xml" href="...">` |
| `type="application/atom+xml"` | `<link type="application/atom+xml" href="...">` |
| `rel="alternate" type="application/rss+xml"` | `<link rel="alternate" type="application/rss+xml" href="...">` |
| `rel="alternate" type="application/atom+xml"` | `<link rel="alternate" type="application/atom+xml" href="...">` |

Resolve relative URLs against the blog's base URL.

### Common Path Heuristics

If no link tags are found, try these paths (append to blog base URL):

- `/feed`
- `/feed.xml`
- `/rss`
- `/rss.xml`
- `/atom.xml`
- `/feeds/posts/default` (Blogger)
- `/index.xml`

**Validation**: Use a HEAD request; accept only if `Content-Type` contains `xml`, `rss`, or `atom`.

---

## Feed Parsing Workarounds

### Entry Content Extraction (Priority Order)

Feeds store content in different fields. Check in this order:

1. `entry.content[0].value` — RSS 2.0 `content:encoded`, Atom `content`
2. `entry.summary` — Atom summary, RSS description (often truncated)
3. `entry.description` — Fallback

If using Python's `feedparser`, `entry.content` is a list of dicts; `entry.summary` and `entry.description` may be plain strings.

### Date Handling

Dates appear in multiple formats:

- `published_parsed` — Tuple `(year, month, day, hour, min, sec, ...)`
- `published` — ISO string
- `updated` / `updated_parsed` — Use when `published` is missing

Handle both tuple and string formats; use a robust date parser (e.g., `dateutil.parser`).

### Link Extraction

- Primary: `entry.link`
- Fallback: `entry.links[0].href` (Atom)
- Make URLs absolute if relative (join against feed's `link` or base URL)

### Pagination

Most feeds do **not** support pagination. A conservative approach: assume no pagination unless you explicitly probe and validate.

Some platforms support:
- `/feed/page/2/`
- `?page=2` or `&page=2`

Probe with HEAD; verify `Content-Type`; only then attempt to parse.

---

## Platform Limits and Supplement Strategy

| Platform | RSS Limit | Strategy |
|----------|-----------|----------|
| Substack | ~20 | RSS + sitemap supplement; merge by URL. |
| Ghost | ~15 | Quick crawl check (first 3 pages); if more posts found, run full crawler and merge. |
| Generic | Varies | Quick check first 3 pages; supplement if `crawled_count > rss_count`. |

**Merge logic**: Deduplicate by post URL. Prefer RSS content (full text) over crawler content when both exist; crawler may only have titles/URLs for list pages.

---

## HTML Content Cleaning

When extracting full post content from HTML (e.g., from feed `content:encoded` or crawled pages):

### Remove

- `script`, `style`, `nav`, `header`, `footer`, `aside`, `noscript`
- `iframe`, `embed`, `object`, `ins` (ads/embeds)

### Preserve Structure

- `p`, `h1`–`h6`, `li`, `blockquote`, `pre`

### Post-Processing

- Decode HTML entities (`&amp;` → `&`, etc.)
- Normalize whitespace (collapse multiple spaces, trim)
- Preserve paragraph breaks for readability

---

## CMS-Specific Crawler Selectors

When crawling non-Substack sites via static HTML, use platform-specific CSS selectors. These are best-effort; platform DOM changes will break them.

### Substack

- Container: `article`, `[class*="post-preview"]`, `a[href*="/p/"]`
- Title: `h1`, `h2`, `[class*="title"]`
- Content: `.post-content`, `[class*="preview"]`

### WordPress

- Container: `article`, `.post`, `.entry`
- Title: `h1.entry-title`, `.entry-header h1`
- Content: `.entry-content`, `.post-content`
- Date: `time[datetime]`
- Tags: `.tags a`, `.entry-tags a`

### Medium

- Container: `article`
- Content: `[data-testid="post-content"]`
- Author: `[data-testid="authorName"]`
- Date: `[data-testid="storyPublishDate"]`

### Ghost

- Container: `article.post`
- Title: `h1.post-title`
- Content: `.post-content`
- Date: `time.published-date`

### Generic Fallback

- Container: `article`, `.post`, `main`
- Content: `.content`, `.post-content`, `.entry-content`
- Date: `time[datetime]`, `.date`, `[class*="date"]`

---

## Summary

| Challenge | What Works |
|-----------|------------|
| Substack limited to 20 posts | RSS + sitemap supplement (`--method sitemap` or auto) for 300+ posts |
| Substack full archive | Sitemap; fetch each post page |
| Substack post links | Query `a[href*="/p/"]` in DOM |
| Feed discovery | HTML link tags + common path heuristics |
| Content in feeds | Check `content`, `summary`, `description` in order |
| Dates | Handle both parsed tuples and string formats |
| Platform limits (Ghost, etc.) | Quick crawl check; supplement if more posts found |
| HTML in content | Remove scripts/ads; preserve structure; decode entities |

---

*Last updated from blog-toolkit implementation. Platform behavior may change over time.*

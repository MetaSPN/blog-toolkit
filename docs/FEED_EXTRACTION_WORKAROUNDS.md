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
3. For JS-heavy platforms (Substack), use a headless browser when needed
4. Probe feed discovery heuristics; validate with Content-Type checks
5. Normalize content and dates across feed formats

---

## Substack-Specific Workarounds

Substack is the trickiest platform. RSS works but is severely limited; the archive page requires JavaScript rendering and infinite-scroll handling.

### RSS Feed Limitations

- **Substack RSS feeds return only ~20 most recent posts** (hard limit)
- Cannot be circumvented via feed pagination—Substack does not support it
- Feed URL is typically `{blog}.substack.com/feed`

**Strategy**: Use RSS for the first 20 posts, then supplement with a browser-based crawl for the full archive.

### JavaScript Rendering

Substack's archive and list pages are heavily JS-rendered. A simple `requests.get()` + BeautifulSoup returns incomplete HTML—post links may be missing or only partially present.

**Workaround**: Use a headless browser (we use [agent-browser](https://github.com/agent-browser/agent-browser)) to render the page before extraction.

**Fallback**: Some Substack pages embed `/p/` links in the initial HTML. When a browser is unavailable, scrape `a[href*="/p/"]` as a best-effort fallback. Results will be incomplete for larger archives.

### Post Discovery Strategy

- **Use `/archive` first**—Substack's archive page (`{blog}.substack.com/archive`) often has a better post listing than the homepage
- **Post URL pattern**: `{blog}.substack.com/p/{slug}`—search for links containing `/p/`

### DOM Extraction (When Using Browser)

Run this in the browser context to extract post links:

```javascript
(function() {
    const allLinks = Array.from(document.querySelectorAll('a[href*="/p/"]'));
    const seenUrls = new Set();
    const posts = [];
    
    allLinks.forEach(link => {
        const href = link.href || link.getAttribute('href');
        if (href && href.includes('/p/') && !seenUrls.has(href)) {
            seenUrls.add(href);
            let title = link.textContent.trim();
            if (!title || title.length < 3) {
                const parent = link.closest('article, [class*="post"], [class*="Post"]');
                if (parent) {
                    const titleElem = parent.querySelector('h1, h2, h3, h4, h5, [class*="title"], [class*="Title"]');
                    if (titleElem) title = titleElem.textContent.trim();
                }
            }
            posts.push({ url: href, title: title || 'Untitled' });
        }
    });
    return posts;
})();
```

### Lazy Loading (Infinite Scroll)

Substack archive uses infinite scroll; content loads as the user scrolls.

- **Workaround**: Scroll down 15+ times with ~3 second delays between scrolls to trigger loading
- Re-run DOM extraction after each scroll batch to capture newly loaded posts
- Deduplicate by URL before merging results

### Modal/Popup Handling

Newsletter signup modals can block content or interfere with extraction. Try to dismiss them (e.g., click "No thanks") before running the extraction script.

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
| Substack | ~20 | If headless browser available: always full browser crawl; merge with RSS. Otherwise: RSS only, accept partial data. |
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

When falling back to static HTML crawl (no headless browser), use platform-specific CSS selectors. These are best-effort; platform DOM changes will break them.

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
| Substack limited to 20 posts | RSS + browser crawl; merge by URL |
| Substack JS-rendered archive | Headless browser; scroll + re-extract for lazy load |
| Substack post links | Query `a[href*="/p/"]` in DOM |
| Feed discovery | HTML link tags + common path heuristics |
| Content in feeds | Check `content`, `summary`, `description` in order |
| Dates | Handle both parsed tuples and string formats |
| Platform limits (Ghost, etc.) | Quick crawl check; supplement if more posts found |
| HTML in content | Remove scripts/ads; preserve structure; decode entities |

---

*Last updated from blog-toolkit implementation. Platform behavior may change over time.*

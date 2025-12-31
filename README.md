# Static Sitemap Generator

Static sitemap generator for HTML websites.

Features:
- Auto-splits large sitemaps (default 25k URLs per part)
- Generates `sitemap_index.xml` pointing to part files
- Last Update Time is based on local filesystem
- Deduplicates images across pages (canonical image URLs)
- Tracks per-part and total stats
- Designed for cron / automation
- Python 3.9+ and BeautifulSoup 4

## Usage

```bash
python sitemap.py --site_base_url=https://example.com/ --site_root=/path/to/html
```

Example cron:
```bash
@daily /usr/bin/python3 /path/to/sitemap.py --site_base_url=https://example.com/ --site_root=/var/www/html
```


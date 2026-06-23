"""Local runner for the RS spider.

Everything is configured here in the file - no terminal arguments. Edit the
CONFIG block below, then just run:

    python Run_RS.py

Each of the 3 machines runs one chunk of sitemaps.json and keeps its own
meta_chunk{N}.json so a crawl can be stopped and resumed. Re-running picks up
where it left off (skips completed sitemaps and already-crawled URLs).
"""

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from cVehicles.spiders.rs_spider import RsSpider

# ======================== CONFIG (edit per machine) ========================
# Set CHUNK to 1, 2 or 3 -> crawls that chunk of sitemaps.json (tracked +
# resumable, writes meta_chunk{N}.json).
CHUNK = 2

# Override the meta file path, or leave None for meta_chunk{CHUNK}.json.
META_PATH = None

# To crawl a single sitemap (or comma-separated list) WITHOUT resume tracking,
# set SITEMAP_URLS to the url(s) below. When set, it takes priority over CHUNK.
# Example: "https://uk.rs-online.com/uk_products_59.xml.gz"
SITEMAP_URLS = None

RETRY_FAILED = f"failed_chunk{CHUNK}.jsonl"

# ===========================================================================


def main():
    process = CrawlerProcess(get_project_settings())
    if RETRY_FAILED:
        process.crawl(RsSpider, retry_failed=RETRY_FAILED, chunk=CHUNK)
    elif SITEMAP_URLS:
        process.crawl(RsSpider, sitemap_urls=SITEMAP_URLS)
    else:
        process.crawl(RsSpider, chunk=CHUNK, meta_path=META_PATH)
    process.start()


if __name__ == "__main__":
    main()

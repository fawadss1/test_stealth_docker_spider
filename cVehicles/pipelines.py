# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter
import json
import logging
import os

# Project root (parent of the Gold_Crawlers package) - local JSONL output lives
# under <root>/output/chunk{N}/.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CrawlersPipeline:
    def process_item(self, item, spider):
        return item


class JsonLinesPerSitemapPipeline:
    """Write one JSONL file per sitemap for local runs.

    Each item carries the sitemap it came from in the private ``_sitemap`` key
    (set by the spider from ``response.meta['sitemap']``). Output is written to
    ``output/chunk{N}/{sitemap_name}.jsonl`` and appended to, so resuming a
    crawl continues the same files.
    """

    def __init__(self):
        self.files = {}
        self.base_dir = None

    def open_spider(self, spider):
        chunk = getattr(spider, 'chunk', None)
        sub = f'chunk{chunk}' if chunk is not None else spider.name
        self.base_dir = os.path.join(PROJECT_ROOT, 'output', sub)
        os.makedirs(self.base_dir, exist_ok=True)
        logging.info("JSONL output dir: %s", self.base_dir)

    @staticmethod
    def _filename(sitemap):
        base = sitemap.rstrip('/').split('/')[-1] if sitemap else 'unknown'
        for ext in ('.xml.gz', '.xml', '.gz'):
            if base.endswith(ext):
                base = base[:-len(ext)]
                break
        return (base or 'items') + '.jsonl'

    def _get_file(self, sitemap):
        if sitemap not in self.files:
            path = os.path.join(self.base_dir, self._filename(sitemap))
            self.files[sitemap] = open(path, 'a', encoding='utf-8')
        return self.files[sitemap]

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        data = dict(adapter.asdict())
        sitemap = data.pop('_sitemap', None) or 'unknown'
        fh = self._get_file(sitemap)
        fh.write(json.dumps(data, ensure_ascii=False) + '\n')
        fh.flush()
        return item

    def close_spider(self, spider):
        for fh in self.files.values():
            try:
                fh.close()
            except OSError:
                pass

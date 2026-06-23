from cVehicles.utils import imgToS3, slugify
from cVehicles.progress import ProgressTracker
import json
import logging
import os
import scrapy
from datetime import datetime, timezone
from itertools import chain
from scrapy.utils.gz import gzip_magic_number, gunzip
from scrapy.selector import Selector
from scrapy.http import XmlResponse
from scrapy.utils.project import get_project_settings
from scrapy.exceptions import DontCloseSpider

settings = get_project_settings()
headers = settings.get('HEADERS')

# Project root (parent of the Gold_Crawlers package) - where sitemaps.json and
# the per-machine meta_chunk*.json files live.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SITEMAPS_FILE = os.path.join(PROJECT_ROOT, 'sitemaps.json')


class RsSpider(scrapy.Spider):
    name = 'Rs_Spider'

    handle_httpstatus_list = [400, 403, 404, 502, 520]

    custom_settings = {
        # 1. Aggressive Base Delay (In seconds)
        # A 5-second base delay with randomization means requests will space out between 2.5 and 7.5 seconds.
        "DOWNLOAD_DELAY": 5.0,
        "RANDOMIZE_DOWNLOAD_DELAY": True,

        # 2. Ultra-low Concurrency
        # Lowering this ensures that even with 5 spiders running, the max total concurrent requests is 10.
        "CONCURRENT_REQUESTS": 6,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 3,

        # 3. Strict AutoThrottle (Adapts to server load)
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 5.0,  # Start slow
        "AUTOTHROTTLE_MAX_DELAY": 60.0,  # Can pause up to a minute if server struggles
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 0.5,  # Target less than 1 concurrent request on average

        # 4. Smart Retries & Backoff
        "RETRY_ENABLED": True,
        "RETRY_TIMES": 3,
        "RETRY_HTTP_CODES": [403, 429, 500, 502, 503, 504],

        # 5. Cookies (Turn off if not strictly required to login, as they track sessions)
        "COOKIES_ENABLED": False,

        # 6. Timeout
        "DOWNLOAD_TIMEOUT": 30,

        "DOWNLOADER_MIDDLEWARES": {
            "scrapy_stealth.middlewares.StealthDownloaderMiddleware": 950,
        },

        # Local output: one JSONL file per sitemap under output/chunk{N}/.
        "ITEM_PIPELINES": {
            "cVehicles.pipelines.JsonLinesPerSitemapPipeline": 300,
        },

        "BROWSER_EXECUTABLE_PATH": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"

        # "STEALTH_PROXIES": ["http://splq77vfo6:78HdqV2Xcx5cJfd_sv@dc.decodo.com:10000"]
    }

    def __init__(self, url=None, sitemap_urls=None, chunk=None, meta_path=None,
                 retry_failed=None, *args, **kwargs):
        super(RsSpider, self).__init__(*args, **kwargs)
        self.url = url
        self.sitemap_urls = sitemap_urls
        self.chunk = int(chunk) if chunk is not None else None
        self.retry_failed = retry_failed
        self.retry_mode = bool(retry_failed)
        self.sitemap_queue = []
        self.retry_requests = []
        self.tracker = None
        self.failed_path = None

        if self.retry_mode:
            # Re-crawl URLs from a failed_*.jsonl file. No tracker: the source
            # sitemaps are already accounted for in meta; we only want output
            # written and a fresh list of still-failing URLs.
            self._setup_retry()
        elif self.chunk is not None:
            all_sitemaps = self._load_chunk(self.chunk)
            meta_path = meta_path or os.path.join(PROJECT_ROOT, f'meta_chunk{self.chunk}.json')
            self.tracker = ProgressTracker(meta_path, chunk=self.chunk)
            self.sitemap_queue = self.tracker.pending_sitemaps(all_sitemaps)
            logging.info(
                "Chunk %s: %d sitemap(s) total, %d pending after resume",
                self.chunk, len(all_sitemaps), len(self.sitemap_queue),
            )
        elif self.sitemap_urls:
            all_sitemaps = [u.strip() for u in self.sitemap_urls.split(',') if u.strip()]
            meta_path = meta_path or os.path.join(PROJECT_ROOT, 'meta_manual.json')
            self.tracker = ProgressTracker(meta_path)
            self.sitemap_queue = self.tracker.pending_sitemaps(all_sitemaps)
            logging.info(
                "Manual sitemap(s): %d total, %d pending after resume",
                len(all_sitemaps), len(self.sitemap_queue),
            )

        if self.tracker is not None:
            # Failed URLs are logged next to the meta file:
            # meta_chunk1.json -> failed_chunk1.jsonl, meta_manual.json -> failed_manual.jsonl
            base = os.path.splitext(os.path.basename(self.tracker.meta_path))[0]
            base = base.replace('meta', 'failed', 1) if base.startswith('meta') else 'failed_' + base
            self.failed_path = os.path.join(os.path.dirname(self.tracker.meta_path), base + '.jsonl')

        # Product pages are fetched with the browser driver; sitemap XML is
        # fetched with the lightweight basic driver.
        self.proxy = {
            "stealth": {
                "driver": "browser",
                "headless": False,
                "static_assets_block": True,
                # "proxy": "http://splq77vfo6:78HdqV2Xcx5cJfd_sv@dc.decodo.com:10000",
                "proxy": "http://spcsx9p37l:8OJr_Fr8syyVotl00v@gate.decodo.com:7000",
                # "proxy": "https://user-rs_test_QUr1t-country-US:7RZYq_u_bmpdTk4f@dc.oxylabs.io:8000",
            }
        }
        self.sitemap_proxy = {
            "stealth": {
                "driver": "basic",
                # "proxy": "http://splq77vfo6:78HdqV2Xcx5cJfd_sv@dc.decodo.com:10000",
                "proxy": "http://spcsx9p37l:8OJr_Fr8syyVotl00v@gate.decodo.com:7000",
                # "proxy": "https://user-rs_test_QUr1t-country-US:7RZYq_u_bmpdTk4f@dc.oxylabs.io:8000",
            }
        }

    @staticmethod
    def _load_chunk(chunk):
        """Return the list of sitemap URLs for the given 1-based chunk index."""
        with open(SITEMAPS_FILE, 'r', encoding='utf-8') as fh:
            chunks = json.load(fh)['chunks']
        if not 1 <= chunk <= len(chunks):
            raise ValueError(f"chunk must be between 1 and {len(chunks)}, got {chunk}")
        return chunks[chunk - 1]

    def _setup_retry(self):
        """Load a failed_*.jsonl file into ``self.retry_requests``.

        Drops ``discontinued`` URLs, de-duplicates, and skips URLs already
        present in this chunk's output JSONL (succeeded on a later run). New
        failures from the retry pass go to ``<name>_retry.jsonl`` so we never
        append to the file we are reading.
        """
        src = self.retry_failed
        if not os.path.isabs(src):
            src = os.path.join(PROJECT_ROOT, src)
        if not os.path.exists(src):
            raise FileNotFoundError('Retry file not found: {}'.format(src))

        base, _ext = os.path.splitext(src)
        self.failed_path = base + '_retry.jsonl'

        already_scraped = self._scraped_urls()

        queued = {}  # url -> sitemap (last seen wins)
        discontinued = set()
        with open(src, 'r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                u = rec.get('url')
                if not u:
                    continue
                if rec.get('reason') == 'discontinued':
                    discontinued.add(u)
                    continue
                queued[u] = rec.get('sitemap')

        skipped_scraped = 0
        for u, sitemap in queued.items():
            if u in already_scraped:
                skipped_scraped += 1
                continue
            self.retry_requests.append((u, sitemap))

        only_discontinued = len(discontinued - set(queued))
        logging.info(
            'Retry mode: %d url(s) queued | skipped %d discontinued, %d already scraped. '
            'New failures -> %s',
            len(self.retry_requests), only_discontinued, skipped_scraped, self.failed_path,
        )

    def _scraped_urls(self):
        """URLs already written to this chunk's output JSONL files."""
        urls = set()
        sub = 'chunk{}'.format(self.chunk) if self.chunk is not None else self.name
        out_dir = os.path.join(PROJECT_ROOT, 'output', sub)
        if not os.path.isdir(out_dir):
            return urls
        for fname in os.listdir(out_dir):
            if not fname.endswith('.jsonl'):
                continue
            try:
                with open(os.path.join(out_dir, fname), 'r', encoding='utf-8') as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            u = json.loads(line).get('url')
                        except json.JSONDecodeError:
                            continue
                        if u:
                            urls.add(u)
            except OSError:
                continue
        logging.info('Retry mode: %d url(s) already in output dir %s', len(urls), out_dir)
        return urls

    def _req_meta(self, **extra):
        """Build product-request meta from the browser proxy plus tracking keys."""
        meta = dict(self.proxy)
        meta.update(extra)
        return meta

    def _sitemap_meta(self, top_sitemap):
        """Build sitemap-request meta using the lightweight basic driver."""
        meta = dict(self.sitemap_proxy)
        meta['top_sitemap'] = top_sitemap
        return meta

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(RsSpider, cls).from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_idle, signal=scrapy.signals.spider_idle)
        spider.crawler = crawler
        return spider

    def spider_idle(self, spider):
        if self.sitemap_queue:
            logging.info(f"Spider idle: found {len(self.sitemap_queue)} sitemap(s) left")
            sitemap = self.sitemap_queue.pop(0)
            req = scrapy.Request(sitemap, callback=self.parse_sitemap,
                                 meta=self._sitemap_meta(sitemap))
            self.crawler.engine.crawl(req)
            raise DontCloseSpider

    def start_requests(self):
        if self.retry_mode:
            if not self.retry_requests:
                logging.info('Retry mode: nothing to re-crawl.')
                return
            for url, sitemap in self.retry_requests:
                yield scrapy.Request(url, callback=self.parse, errback=self.errback,
                                     meta=self._req_meta(sitemap=sitemap))

        elif self.url:
            yield scrapy.Request(self.url, callback=self.parse, meta=self.proxy)

        elif self.chunk is not None or self.sitemap_urls:
            if not self.sitemap_queue:
                logging.info('Nothing pending to crawl (all sitemaps completed).')
                return
            sitemap = self.sitemap_queue.pop(0)
            yield scrapy.Request(sitemap, callback=self.parse_sitemap,
                                 meta=self._sitemap_meta(sitemap))

        else:
            logging.error('No url, chunk or sitemap urls supplied. Nothing to do.')

    def parse_sitemap(self, response):
        logging.info('======== Parsing Sitemap: {} ========'.format(response.url))
        # The top-level sitemap (from the chunk) that this response belongs to;
        # all product URLs found here are tracked against it for resume.
        top_sitemap = response.meta.get('top_sitemap', response.url)

        body = self._get_sitemap_body(response)
        sel = Selector(text=body)
        sel.remove_namespaces()

        nested, product_urls = [], []
        for url in sel.xpath('//loc/text()').getall():
            if url.endswith('.xml') or url.endswith('.xml.gz'):
                nested.append(url)
            elif 'uk.rs-online.com/web/p/' in url:
                product_urls.append(url)
            else:
                logging.info('Ignoring sitemap url: {}'.format(url))

        already = self.tracker.crawled_urls(top_sitemap)
        remaining = [u for u in product_urls if u not in already]
        self.tracker.start_sitemap(top_sitemap, len(product_urls))
        logging.info('Sitemap %s: %d product url(s), %d remaining after resume',
                     top_sitemap, len(product_urls), len(remaining))

        # Everything already crawled and nothing nested left -> mark complete.
        if not remaining and not nested:
            self.tracker.complete_sitemap(top_sitemap)
            return

        for url in nested:
            yield scrapy.Request(url, callback=self.parse_sitemap,
                                 meta=self._sitemap_meta(top_sitemap))
        for url in remaining:
            yield scrapy.Request(url, callback=self.parse, errback=self.errback,
                                 meta=self._req_meta(sitemap=top_sitemap))

    @staticmethod
    def _get_sitemap_body(response):
        if isinstance(response, XmlResponse):
            return response.body
        elif gzip_magic_number(response):
            return gunzip(response.body)
        elif response.url.endswith('.xml') or response.url.endswith('.xml.gz'):
            return response.body

    def parse(self, response):
        """Crawl a product page and record it against its parent sitemap.

        Records the URL whether or not an item was produced (an error status or
        discontinued product still counts as 'crawled'), so a sitemap can reach
        completion. Network failures are recorded via ``errback``.
        """
        item, reason = None, None
        try:
            item, reason = self._parse_product(response)
        except Exception as exc:
            reason = 'exception: {!r}'.format(exc)
            logging.error('Error parsing %s: %r', response.url, exc)

        self._track(response, success=item is not None)

        if item is None:
            # Every URL that produced no item is logged with its reason
            # (e.g. 'discontinued', 'HTTP 404', 'no __NEXT_DATA__') so the
            # failed file mirrors the error count in the meta file.
            self._record_failure(response.url, response.meta.get('sitemap'), reason or 'unknown')
            return None

        # Tag the item with its sitemap so the JSONL pipeline can route it.
        item['_sitemap'] = response.meta.get('sitemap')
        return item

    def errback(self, failure):
        request = failure.request
        logging.error('Request failed: {} ({})'.format(request.url, failure.value))
        sitemap = request.meta.get('sitemap')
        if self.tracker is not None and sitemap:
            self.tracker.record_url(sitemap, request.url, success=False)
        self._record_failure(request.url, sitemap, repr(failure.value))

    def _track(self, response, success):
        if self.tracker is None:
            return
        sitemap = response.meta.get('sitemap')
        if sitemap:
            self.tracker.record_url(sitemap, response.url, success=success)

    def _record_failure(self, url, sitemap, reason):
        """Append a failed URL to failed_*.jsonl for later retry."""
        if not self.failed_path:
            return
        record = {
            'url': url,
            'sitemap': sitemap,
            'reason': reason,
            'ts': datetime.now(timezone.utc).isoformat(),
        }
        with open(self.failed_path, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + '\n')

    def _parse_product(self, response):
        logging.info('======== Parsing Url: {} ========'.format(response.url))

        if response.status in self.handle_httpstatus_list:
            logging.error('({}) ----> Got Error Response status: {}'.format(response.url, response.status))
            return None, 'HTTP {}'.format(response.status)

        ldjson = response.xpath(
            '//script[@type="application/ld+json" and @data-testid="product-list-script"]/text()'
        ).get(default='{}')
        data = json.loads(ldjson)
        if not data:
            logging.warning('No data found for url: {}'.format(response.url))
            return None, 'no ld+json data'

        if data['offers']['availability'].endswith('Discontinued'):
            logging.info('Product: {} is discontinued'.format(data['name']))
            return None, 'discontinued'

        name = data['name']
        rs_partno = data.get('sku')
        mpn = data.get('mpn') or rs_partno

        brand = data.get('brand').get('name')
        attributes = data.get('additionalProperty')
        if attributes:
            attributes = {attr['name']: attr['value'] for attr in attributes}

        _data = response.xpath("//script[@id='__NEXT_DATA__']/text()").get()
        if not _data:
            return None, 'no __NEXT_DATA__'

        json_data = json.loads(_data)['props']['pageProps']
        article = json_data['articleResult']['data']['article']

        breadcrumb = [c['label'].strip() for c in article['taxonomy']]

        imgList = []
        base_image_url = "https://res.cloudinary.com/rsc/image/upload/{}"
        if 'images' in article:
            for img in article['images']:
                image_url = base_image_url.format(img.strip())
                img = img.split('.')[0][-5:]
                if mpn:
                    fileName = f'{slugify(mpn)}{img}.jpg'
                else:
                    fileName = f'{slugify(rs_partno)}{img}.jpg'
                imgList.append({'original': image_url, 'path': imgToS3('rs', image_url, fileName)})

        short_desc, long_desc = self.parse_description(response)

        availability = 0
        stock_data = json_data['productAvailabilityResult']
        if stock_data:
            availability = stock_data['data']['quantity']

        stock_status = "Back Order"
        if availability and availability > 1:
            stock_status = "In Stock"

        rohsStatus = article['rohsStatus']
        rohs = rohsStatus == "Y"

        documents = []
        for document in article["documents"]:
            displayname = document['title']
            href = document['url']
            if displayname and href:
                key = href.split('/')[-1]
                documents.append({displayname: {'url': href, 'key': key}})

        pricing = {
            'currency': article['prices']['currencyCode'],
            'ranges': self.get_price_ranges(response)
        }

        item = {
            'url': response.url,
            'stockStatus': stock_status,
            'productHeading': name,
            'mpn': mpn,
            'mpnList': [rs_partno],
            'quoted': False,
            'quantity': availability,
            'manufacturer': brand,
            'leadTime': 'N/A',
            'rohs': rohs,
            'categories': breadcrumb,
            'shortDesc': short_desc,
            'longDesc': long_desc,
            'attributes': attributes,
            'documents': documents,
            'prices': pricing,
            'image_urls': imgList,
        }
        print(item)
        return item, None

    def closed(self, reason):
        if self.tracker is not None:
            self.tracker.flush()
            done = len(self.tracker.data['completed_sitemaps'])
            logging.info("Spider closed (%s). %d sitemap(s) completed. Meta: %s",
                         reason, done, self.tracker.meta_path)

    @staticmethod
    def get_price_ranges(response):
        ranges = []
        price_breaks = response.xpath("//tr[contains(@data-testid,'price-breaks-row')]")
        for row in price_breaks:
            quantity = row.xpath('.//td[@data-testid="price-breaks-quantity"]/text()').get()
            price = row.xpath('.//span[@data-testid="price-breaks-price"]/text()').get()

            if price:
                price = price.replace("£", "")

            if quantity:
                if "-" in quantity:
                    from_val, to_val = quantity.split(" - ")
                elif "+" in quantity:
                    from_val, to_val = quantity.replace(" +", ""), ""
                else:
                    continue

                ranges.append({
                    "from": from_val.strip(),
                    "to": to_val.strip(),
                    "price": price
                })

        return ranges

    @staticmethod
    def parse_description(response):
        """
        Parses the description of an article from the provided response object.

        The method extracts JSON data embedded in an HTML script tag from the response,
        then parses the relevant fields to construct a short and detailed description.
        The information is derived based on the structure of the content, where descriptions
        can either be under 'subrange' or 'unique' nodes.

        :param response: The response object containing the HTML page to parse.
        :type response: scrapy.http.Response
        :return: A tuple containing the short description and the detailed description as a string.
        :rtype: Tuple[str, str]
        """
        _data = response.xpath("//script[@id='__NEXT_DATA__']/text()").get()
        if not _data:
            return ""

        data = json.loads(_data)
        data = data.get("props", {}).get("pageProps", {}).get("articleResult", {}).get("data", {}).get("article", {})

        short_description = ""
        if 'longDescription' in data:
            short_description = data['longDescription']

        desc_content = data["descriptiveContent"]
        if not desc_content:
            return short_description, ""

        try:
            if 'subrange' in desc_content:
                description_content = desc_content["subrange"]["content"]
                description = [desc["value"] for desc in description_content if desc]
                cleaned_description = list(chain.from_iterable(description))
            else:
                description_content = desc_content["unique"]["content"]
                description = [desc["value"] for desc in description_content if desc]
                cleaned_description = list(chain.from_iterable(description))
        except Exception as e:
            cleaned_description = ""
            logging.error(f"Error Occured while parsing description: {e} of product: {response.url}")

        return short_description, "\n".join(cleaned_description)

    # def closed(self, reason):
    #     import requests
    #
    #     if reason == 'finished':
    #
    #         if self.settings.get("JOBDIR"):
    #             webhock_url = settings.get('WEBHOOK_LIVE_URL')
    #         else:
    #             webhock_url = settings.get('WEBHOOK_LOCAL_URL')
    #
    #         try:
    #             response = requests.post(webhock_url, json={'project_id': settings.get('PROJECT_ID'), 'spider_id': self.name,
    #                                                         'source': 'rs', 'img_dir': 'rs', 'link': 'https://uk.rs-online.com',
    #                                                         'lang': 'en'},
    #                                      headers={'Content-Type': 'application/json'},
    #                                      timeout=10)
    #             response.raise_for_status()
    #             logging.info(f"Webhook url '{webhock_url}' triggered successfully for spider: {self.name}")
    #
    #         except Exception as e:
    #             logging.error(f"Failed to trigger webhook for spider {self.name}: {str(e)}")
    #         finally:
    #             logging.info(f"Spider closed: {self.name}, reason: {reason}")

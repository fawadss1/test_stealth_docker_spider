import scrapy


class DemoSpider(scrapy.Spider):
    name = "demo"
    start_urls = ["https://ip.decodo.com/ip"]
    handle_httpstatus_list = [404, 403]

    def __init__(self, url=None, proxy=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if url:
            self.start_urls = [url]
        self.proxy = ''
        if proxy:
            self.proxy = proxy

    def start_requests(self):
        for _ in range(50):
            yield scrapy.Request(
                self.start_urls[0],
                meta={
                    "stealth": {
                        "driver": "browser",
                        "headless": False,
                        "proxy": self.proxy,
                        # "rotate_proxy": True,
                    }
                },
                callback=self.parse,
                dont_filter=True,
            )

    def parse(self, response):
        ldjson = response.xpath(
            '//script[@type="application/ld+json" and @data-testid="product-list-script"]/text()'
        ).get(default='{}')

        item = {
            'ldjson': ldjson,
            'flags': response.flags,
            'content': response.text,
            'status': response.status,
        }
        print(item)
        return item

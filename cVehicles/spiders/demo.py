import scrapy


class DemoSpider(scrapy.Spider):
    name = "demo"
    # start_urls = ["http://quotes.toscrape.com"]
    start_urls = ["https://httpbin.org/ip"]
    handle_httpstatus_list = [404, 403]

    def __init__(self, url=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if url:
            self.start_urls = [url]

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                meta={
                    "stealth": {
                        "driver": "browser",
                        "headless": False,
                        "rotate_proxy": True,
                    }
                },
                callback=self.parse,
            )

    def parse(self, response):
        print(response.text)
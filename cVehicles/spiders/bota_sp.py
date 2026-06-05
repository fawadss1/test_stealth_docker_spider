import scrapy
from botasaurus_driver import Driver


class BotaSpider(scrapy.Spider):
    name = 'bota_spider'
    start_urls = ['http://quotes.toscrape.com/js']

    handle_httpstatus_list = [404, 403]

    def __init__(self, url=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.driver = Driver(
            # headless=False,
            proxy="http://spcsx9p37l:8OJr_Fr8syyVotl00v@gb.decodo.com:30000",
            block_images_and_css=True,
            # chrome_executable_path=self.executable,
            arguments=[
                # Original anti-detection flags
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-client-side-phishing-detection",
                "--disable-sync",
                "--no-first-run",
                "--metrics-recording-only",
                # Optimisation #5 — disable unused Chrome subsystems to reduce
                # per-page CPU and memory overhead
                "--disable-extensions",
                "--disable-plugins",
                "--disable-default-apps",
                "--disable-translate",
                "--disable-hang-monitor",
                "--disable-prompt-on-repost",
                "--disable-domain-reliability",
                "--no-default-browser-check",
                "--autoplay-policy=no-user-gesture-required",
                "--no-sandbox",
            ]
        )
        if url:
            self.start_urls = [url]

    def start_requests(self):
        for _ in range(50):
            yield scrapy.Request(
                self.start_urls[0],
                callback=self.parse,
                dont_filter=True,
            )

    def parse(self, response):
        self.driver.google_get(response.url)
        elem = self.driver.select(
            'script[type="application/ld+json"][data-testid="product-list-script"]'
        )
        sc = elem.text if elem else None

        return {
            'script': sc,
            'content': self.driver.page_html,
        }

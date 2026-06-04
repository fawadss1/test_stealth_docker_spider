BOT_NAME = 'cVehicles'

SPIDER_MODULES = ['cVehicles.spiders']
NEWSPIDER_MODULE = 'cVehicles.spiders'

ROBOTSTXT_OBEY = False

LOG_LEVEL = "ERROR"

DOWNLOADER_MIDDLEWARES = {
    "scrapy_stealth.StealthDownloaderMiddleware": 950,
}

BROWSER_NO_SANDBOX = True

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"

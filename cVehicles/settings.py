BOT_NAME = 'cVehicles'

SPIDER_MODULES = ['cVehicles.spiders']
NEWSPIDER_MODULE = 'cVehicles.spiders'

ROBOTSTXT_OBEY = False

LOG_LEVEL = "ERROR"

DOWNLOADER_MIDDLEWARES = {
    "scrapy_stealth.middlewares.StealthDownloaderMiddleware": 950,
}

SIMPLE_PROXY = {}

STEALTH_PROXIES = [
    "http://spcsx9p37l:8OJr_Fr8syyVotl00v@gb.decodo.com:30000"
]

BROWSER_NO_SANDBOX = True

BROWSER_EXECUTABLE_PATH = "C:\Program Files\BraveSoftware\Brave-Browser\Application\\brave.exe"
# BROWSER_EXECUTABLE_PATH = "/usr/bin/brave-browser"

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"

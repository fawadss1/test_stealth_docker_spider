from scrapy.utils.project import get_project_settings
from cVehicles.spiders import demo, bota_sp
from scrapy.crawler import CrawlerProcess

process = CrawlerProcess(get_project_settings())

# process.crawl(demo.DemoSpider)
# process.crawl(demo.DemoSpider,  url='https://uk.rs-online.com/web/p/tool-box-accessories/2556102')
process.crawl(bota_sp.BotaSpider,  url='https://uk.rs-online.com/web/p/tool-box-accessories/2556102')

process.start()

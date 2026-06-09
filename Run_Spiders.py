from scrapy.utils.project import get_project_settings
from cVehicles.spiders import demo, bota_sp
from scrapy.crawler import CrawlerProcess

process = CrawlerProcess(get_project_settings())

process.crawl(demo.DemoSpider, proxy="https://user-rs_test_QUr1t-country-US:7RZYq_u_bmpdTk4f@dc.oxylabs.io:8000")
# process.crawl(demo.DemoSpider,  url='https://uk.rs-online.com/web/p/tool-box-accessories/2556102', proxy="https://user-rs_test_QUr1t-country-US:7RZYq_u_bmpdTk4f@dc.oxylabs.io:8000")
# process.crawl(bota_sp.BotaSpider,  url='https://uk.rs-online.com/web/p/tool-box-accessories/2556102')

process.start()

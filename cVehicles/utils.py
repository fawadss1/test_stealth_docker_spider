from .settings import SIMPLE_PROXY
from scrapy.exceptions import CloseSpider
from email.mime.text import MIMEText
from base64 import b64decode
from io import BytesIO
import unicodedata
import requests
import logging
import smtplib
import boto3
import html
import re
import hashlib
import os
from urllib.parse import urlparse, quote
from concurrent.futures import ThreadPoolExecutor
import threading
from botocore.exceptions import ClientError

# Global instances for connection reuse
_s3_client = None
_session = None
_thread_local = threading.local()


def get_s3_client():
    """Get or create a reusable S3 client with connection pooling."""
    global _s3_client, _session
    if _s3_client is None:
        _session = boto3.session.Session(
            aws_access_key_id=str(os.getenv("AWS_ACCESS_KEY_ID")),
            aws_secret_access_key=str(os.getenv("AWS_SECRET_ACCESS_KEY")),
            region_name=str(os.getenv("AWS_REGION", "eu-west-1"))
        )
        _s3_client = _session.client('s3')
    return _s3_client


def get_requests_session():
    """Get or create a thread-local requests session for connection pooling."""
    if not hasattr(_thread_local, 'session'):
        _thread_local.session = requests.Session()
        # Configure connection pooling
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=3
        )
        _thread_local.session.mount('http://', adapter)
        _thread_local.session.mount('https://', adapter)
    return _thread_local.session


def get_image_key(url):
    """Generate a unique key for the image based on URL hash."""
    return hashlib.sha1(url.encode()).hexdigest()


def check_image_exists(s3_client, bucket, key):
    """Check if image already exists in S3."""
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError:
        return False


def download_image_data(url, site=None, proxy=False, timeout=30):
    """Download image data with optimized settings."""
    session = get_requests_session()
    proxies = SIMPLE_PROXY if proxy else None
    verify = not proxy

    try:
        if site == "Farnell":
            response = session.post(
                "https://api.zyte.com/v1/extract",
                auth=("6404abe3b1b34abaa8bc7371d84831f6", ""),
                json={"url": url, "httpResponseBody": True},
                timeout=timeout
            )
            response.raise_for_status()
            return b64decode(response.json().get("httpResponseBody", b""))
        else:
            response = session.get(
                url,
                stream=True,
                proxies=proxies,
                verify=verify,
                timeout=timeout
            )
            response.raise_for_status()

            # Stream download with size limit (10MB max)
            max_size = 10 * 1024 * 1024
            downloaded_size = 0
            chunks = []

            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    downloaded_size += len(chunk)
                    if downloaded_size > max_size:
                        raise ValueError(f"Image too large: {downloaded_size} bytes")
                    chunks.append(chunk)

            return b''.join(chunks)

    except Exception as e:
        logging.info(f"Failed to download image from {url}: {e}")


def imgToS3(dire, src, name, site=None, proxy=False, skip_existing=True):
    """
    Optimized image upload to S3 with caching, connection pooling, and better error handling.

    Args:
        dire: Directory name
        src: Image source URL
        name: Image filename
        site: Site name for special handling
        proxy: Whether to use proxy
        skip_existing: Skip upload if image already exists

    Returns:
        str: S3 key if successful, None if failed
    """
    if not src or not name:
        logging.warning("Invalid src or name provided")
        return None

    img_dest = f'{dire}-prod/{name}'
    bucket = 'products-management-dashboard'

    try:
        s3_client = get_s3_client()

        # Check if image already exists to avoid unnecessary downloads
        if skip_existing and check_image_exists(s3_client, bucket, img_dest):
            return img_dest

        # Download image data
        image_data = download_image_data(src, site=site, proxy=proxy)

        if not image_data:
            return None

        # Determine content type based on image data
        content_type = 'image/jpeg'  # default
        if image_data.startswith(b'\x89PNG'):
            content_type = 'image/png'
        elif image_data.startswith(b'GIF'):
            content_type = 'image/gif'
        elif image_data.startswith(b'\xff\xd8\xff'):
            content_type = 'image/jpeg'

        def _sanitize_metadata_value(val):
            """Ensure S3 metadata value is ASCII-only by URL-encoding if needed."""
            if val is None:
                return ''
            if isinstance(val, str):
                try:
                    val.encode('ascii')
                    return val
                except UnicodeEncodeError:
                    return quote(val)
            return str(val)

        # Upload to S3 with proper content type
        with BytesIO(image_data) as data:
            s3_client.upload_fileobj(
                data,
                bucket,
                img_dest,
                ExtraArgs={
                    'ContentType': content_type,
                    'CacheControl': 'max-age=31536000',  # Cache for 1 year
                    'Metadata': {
                        'source_url': _sanitize_metadata_value(src),
                        'site': _sanitize_metadata_value(site)
                    }
                }
            )

        return img_dest

    except Exception as e:
        logging.info(f"Failed to upload image {src} to S3: {e}")
        return None


def slugify(text):
    text = re.sub(r'\W+', '-', text).strip('-').lower()
    return text


def cleanText(text):
    cleanText = unicodedata.normalize('NFKD', html.unescape(text)).encode('ascii', 'ignore').decode('ascii')
    return cleanText


def validate_item(self, item, product_link):
    """Validate critical fields and handle errors."""
    critical_fields = {
        'mpn': item['mpn'],
        'manufacturer': item['manufacturer'],
    }

    for field_name, field_value in critical_fields.items():
        if field_value == "N/A" or not field_value:
            self.error_count += 1
            logging.error(f"Item error detected for {product_link} at {field_name}")

        if self.error_count >= 10:
            logging.info(f"Error count ({self.error_count}) exceeded. Terminating spider.")
            raise CloseSpider(f'terminated due to too many errors at: {field_name}')

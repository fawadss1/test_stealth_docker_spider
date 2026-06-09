"""Resume / progress tracking for local sitemap crawls.

Each machine runs one chunk of ``sitemaps.json`` and owns a single
``meta_chunk{N}.json`` file. The file keeps:

* ``completed_sitemaps`` - sitemaps whose every product URL has been crawled.
* ``in_progress``        - per-sitemap dict holding the URLs crawled *so far*.

As soon as a sitemap is finished its URL list is dropped and the sitemap is
appended to ``completed_sitemaps`` so the file stays small even though the site
has millions of products.
"""

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone


class ProgressTracker:
    def __init__(self, meta_path, chunk=None):
        self.meta_path = os.path.abspath(meta_path)
        self._lock = threading.Lock()
        self.data = self._load()
        if chunk is not None:
            self.data["chunk"] = chunk

    # ------------------------------------------------------------------ load
    def _load(self):
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                data.setdefault("completed_sitemaps", [])
                data.setdefault("in_progress", {})
                data.setdefault("stats", {"items_scraped": 0, "errors": 0})
                logging.info(
                    "Loaded meta '%s': %d completed, %d in-progress sitemap(s)",
                    self.meta_path,
                    len(data["completed_sitemaps"]),
                    len(data["in_progress"]),
                )
                return data
            except (json.JSONDecodeError, OSError) as exc:
                logging.error("Could not read meta '%s': %s - starting fresh", self.meta_path, exc)
        return {
            "chunk": None,
            "completed_sitemaps": [],
            "in_progress": {},
            "stats": {"items_scraped": 0, "errors": 0},
            "last_updated": None,
        }

    # -------------------------------------------------------------- queries
    def is_completed(self, sitemap_url):
        return sitemap_url in self.data["completed_sitemaps"]

    def pending_sitemaps(self, all_sitemaps):
        """Return the sitemaps from ``all_sitemaps`` that are not done yet."""
        return [s for s in all_sitemaps if s not in self.data["completed_sitemaps"]]

    def crawled_urls(self, sitemap_url):
        entry = self.data["in_progress"].get(sitemap_url)
        return set(entry["crawled_urls"]) if entry else set()

    # --------------------------------------------------------------- writes
    def start_sitemap(self, sitemap_url, total_urls):
        """Register (or refresh on resume) a sitemap's total product count."""
        with self._lock:
            entry = self.data["in_progress"].setdefault(
                sitemap_url, {"total_urls": 0, "crawled_urls": []}
            )
            entry["total_urls"] = total_urls
            self._save_locked()

    def record_url(self, sitemap_url, product_url, success=True):
        """Mark one product URL of ``sitemap_url`` as processed."""
        with self._lock:
            entry = self.data["in_progress"].setdefault(
                sitemap_url, {"total_urls": 0, "crawled_urls": []}
            )
            if product_url not in entry["crawled_urls"]:
                entry["crawled_urls"].append(product_url)
            if success:
                self.data["stats"]["items_scraped"] += 1
            else:
                self.data["stats"]["errors"] += 1

            total = entry.get("total_urls", 0)
            if total and len(entry["crawled_urls"]) >= total:
                self._complete_locked(sitemap_url)
            # Persist immediately after every product so the meta file always
            # reflects exactly what has been crawled (durable resume point).
            self._save_locked()

    def complete_sitemap(self, sitemap_url):
        """Force-complete a sitemap (e.g. resume found everything already done)."""
        with self._lock:
            self._complete_locked(sitemap_url)
            self._save_locked()

    def _complete_locked(self, sitemap_url):
        if sitemap_url not in self.data["completed_sitemaps"]:
            self.data["completed_sitemaps"].append(sitemap_url)
            logging.info("Sitemap completed: %s", sitemap_url)
        # Drop the URL list - keeps the meta file small.
        self.data["in_progress"].pop(sitemap_url, None)

    def flush(self):
        with self._lock:
            self._save_locked()

    # ---------------------------------------------------------- persistence
    def _save_locked(self):
        self.data["last_updated"] = datetime.now(timezone.utc).isoformat()
        directory = os.path.dirname(self.meta_path)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.meta_path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

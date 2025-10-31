import os
import shelve

import time
import hashlib

from threading import Thread, RLock
from queue import Queue, Empty
from urllib.parse import urlparse


from utils import get_logger, get_urlhash, normalize
from scraper import is_valid

class Frontier(object):
    def __init__(self, config, restart):
        self.logger = get_logger("FRONTIER")
        self.config = config
        self.to_be_downloaded = Queue()
        self.lock = RLock()

        # Politeness: last access time per domain
        self.domain_last_access = {}

        # Duplicate detection
        self.visited_hashes = set()
        self.visited_shingles = []


        # Load/create save file
        if not os.path.exists(self.config.save_file) and not restart:
            self.logger.info(f"No save file found, starting from seed.")
        elif os.path.exists(self.config.save_file) and restart:
            self.logger.info(f"Deleting existing save file {self.config.save_file}.")
            os.remove(self.config.save_file)

        self.save = shelve.open(self.config.save_file)

        # Add seed URLs if restarting, or load from save
        if restart:
            for url in self.config.seed_urls:
                self.add_url(url)
        else:
            self._parse_save_file()
            if not self.save:
                for url in self.config.seed_urls:
                    self.add_url(url)

        print("TO_BE_DOWNLOADED after init:", list(self.to_be_downloaded.queue))


    def _parse_save_file(self):
        ''' This function can be overridden for alternate saving techniques. '''
        tbd_count = 0
        for url, completed in self.save.values():
            if not completed and is_valid(url):
                self.to_be_downloaded.put(url)
                tbd_count += 1
        self.logger.info(f"Found {tbd_count} URLs to download from save file.")
    
    def get_tbd_url(self):
        while True:
            try:
                url = self.to_be_downloaded.get(timeout=1)
            except Empty:
                return None

            domain = urlparse(url).netloc
            with self.lock:
                last_time = self.domain_last_access.get(domain, 0)
                elapsed = time.time() - last_time
                if elapsed < 0.5:  # 500ms politeness
                    self.to_be_downloaded.put(url)
                    time.sleep(0.5 - elapsed)
                    continue
                self.domain_last_access[domain] = time.time()
                return url


   
    def add_url(self, url, html_content=None):
        url = normalize(url)
        urlhash = get_urlhash(url)

        with self.lock:
            if urlhash in self.save:
                return  # already seen

            # Check exact duplicate if html provided
            if html_content:
                h = hashlib.md5(html_content.encode()).hexdigest()
                if h in self.visited_hashes:
                    return
                self.visited_hashes.add(h)

                # Check near-duplicate using shingles
                if self.is_near_duplicate(html_content):
                    return

            self.save[urlhash] = (url, False)
            self.save.sync()
            self.to_be_downloaded.put(url)

       
  

    
    def mark_url_complete(self, url):
        urlhash = get_urlhash(url)
        with self.lock:
            if urlhash not in self.save:
                # This should not happen.
                self.logger.error(
                    f"Completed url {url}, but have not seen it before.")

            self.save[urlhash] = (url, True)
            self.save.sync()

    def is_near_duplicate(self, html, k=5, threshold=0.8):
        words = html.split()
        shingles = set(tuple(words[i:i+k]) for i in range(len(words)-k+1))
        for old in self.visited_shingles:
            jaccard = len(shingles & old) / len(shingles | old)
            if jaccard >= threshold:
                return True
        self.visited_shingles.append(shingles)
        return False

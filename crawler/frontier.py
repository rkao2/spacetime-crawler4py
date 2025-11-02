import os
import shelve

from threading import Thread, RLock
from queue import Queue, Empty

from utils import get_logger, get_urlhash, normalize
from scraper import is_valid

class Frontier(object):
    def __init__(self, config, restart):
        self.logger = get_logger("FRONTIER")
        self.config = config
        self.to_be_downloaded = []
        self.lock = RLock()

        
        print("Seed URLs:", self.config.seed_urls)
        if not os.path.exists(self.config.save_file) and not restart:
            # Save file does not exist, but request to load save.
            self.logger.info(
                f"Did not find save file {self.config.save_file}, "
                f"starting from seed.")
        elif os.path.exists(self.config.save_file) and restart:
            # Save file does exists, but request to start from seed.
            self.logger.info(
                f"Found save file {self.config.save_file}, deleting it.")
            os.remove(self.config.save_file)
        # Load existing save file, or create one if it does not exist.
        self.save = shelve.open(self.config.save_file)
        if restart:
            for url in self.config.seed_urls:
                self.add_url([url, 0])
        else:
            # Set the frontier state with contents of save file.
            self._parse_save_file()
            if not self.save:
                for url in self.config.seed_urls:
                    self.add_url([url, 0])

        print("TO_BE_DOWNLOADED after init:", self.to_be_downloaded)

    def _parse_save_file(self):
        ''' This function can be overridden for alternate saving techniques. '''
        total_count = len(self.save)
        tbd_count = 0
        for url, depth, completed in self.save.values():
            if not completed and is_valid(url):
                self.to_be_downloaded.append([url, depth])
                tbd_count += 1
        self.logger.info(
            f"Found {tbd_count} urls to be downloaded from {total_count} "
            f"total urls discovered.")

    def get_tbd_url(self):
        with self.lock:
            if self.to_be_downloaded:
                return self.to_be_downloaded.pop()
            return None

   
    def add_url(self, url):
        inner_url = normalize(url[0])
        # print("Normalized URL: ", inner_url)
        urlhash = get_urlhash(inner_url)
        # print("URL hash:", urlhash)
        # print("Already in save?", urlhash in self.save)
        
        url_with_depth = [inner_url, url[1]]
        
        with self.lock:  
            if urlhash not in self.save:
                self.save[urlhash] = (inner_url, url[1], False)
                self.save.sync()
                self.to_be_downloaded.append(url_with_depth)
                print("Added to to_be_downloaded")
       
        
    
    def mark_url_complete(self, url):
        url = url[0]
        depth = url[1]
        urlhash = get_urlhash(url)

        with self.lock:
            if urlhash not in self.save:
                # This should not happen.
                self.logger.error(
                    f"Completed url {url}, but have not seen it before.")

        self.save[urlhash] = (url, depth, True)
        self.save.sync()

    
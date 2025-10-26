import re
from urllib.parse import urljoin, urldefrag, urlparse
from bs4 import BeautifulSoup
import time
import hashlib
from collections import defaultdict

last_request_time = defaultdict(float)
visited_content_hashes = set()
# POLITENESS_DELAY = 2  # seconds
# MIN_TEXT_LENGTH = 200  # minimum text length to consider page valuable
MAX_HTML_SIZE = 2_000_000  # max page size in bytes (2MB)

visited_urls = set()
last_crawl_time = {}

# ALLOWED_DOMAINS = ("ics.uci.edu", "cs.uci.edu", "informatics.uci.edu", "stat.uci.edu")

def scraper(url, resp):

    global visited_urls
    url = normalize_url(url)
    
    if url in visited_urls:
        print(f"[SCRAPER] Skipping already visited: {url}")
        return []
    visited_urls.add(url)
    

    
    # Check if page is valuable (text-rich, non-duplicate, reasonable size)
    if not resp.raw_response or resp.status != 200:
        return []

    content = resp.raw_response.content
    if len(content) > MAX_HTML_SIZE:
        print(f"[SCRAPER] Skipping {url} because it is too large")
        return []

    soup = BeautifulSoup(content, "html.parser")
    text = soup.get_text(strip=True)
    # if len(text) < MIN_TEXT_LENGTH:
    #     print(f"[SCRAPER] Skipping {url} because it has too little text")
    #     return []

    # Check for duplicate content
    content_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
    if content_hash in visited_content_hashes:
        print(f"[SCRAPER] Skipping {url} because content is duplicate")
        return []
    visited_content_hashes.add(content_hash)

    

    # Extract and normalize links
    links = extract_next_links(url, resp)
    return [link for link in links if is_valid(link) and link not in visited_urls]


 # resp.url: the actual url of the page
    # resp.status: the status code returned by the server. 200 is OK, you got the page. Other numbers mean that there was some kind of problem.
    # resp.error: when status is not 200, you can check the error here, if needed.
    # resp.raw_response: this is where the page actually is. More specifically, the raw_response has two parts:
    #         resp.raw_response.url: the url, again
    #         resp.raw_response.content: the content of the page!
    # Return a list with the hyperlinks (as strings) scrapped from resp.raw_response.content


def normalize_url(url):
    parsed = urlparse(url)
    clean_path = re.sub(r"/+", "/", parsed.path)  # remove multiple slashes
    clean_query = "&".join(
        sorted([
            q for q in parsed.query.split("&")
            if not re.match(r"(utm_|sessionid|ref|fbclid|PHPSESSID)", q)
        ])
    )
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=clean_path,
        query=clean_query,
        fragment=""  # drop fragment
    )
    return normalized.geturl()


def extract_next_links(url, resp):
    # Implementation required.
    # url: the URL that was used to get the page
    
    if resp.status != 200 or not resp.raw_response:
        return []

    content = resp.raw_response.content
    soup = BeautifulSoup(content, "html.parser")
    links = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        joined = urljoin(url, href)
        normalized = normalize_url(joined)
        if is_valid(normalized):
            links.add(normalized)

    print(f"[SCRAPER] Extracted {len(links)} links from {url}")

    return list(links)

def is_valid(url):
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        
        # Check allowed domains
        # if "wics" in parsed.netloc:
        #     return False
        if "uci.edu" not in parsed.netloc:
            return False
        
        # Filter out non-HTML resources
        if re.search(r"(page|offset|start|p)=\d{2,}", parsed.query.lower()):
            return False

        return True

    except TypeError:
        print("TypeError for ", url)
        return False

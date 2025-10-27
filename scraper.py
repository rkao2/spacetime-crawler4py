import re
from urllib.parse import urljoin, urldefrag, urlparse
import urllib.robotparser as my_robot
from bs4 import BeautifulSoup
import time
import hashlib
import requests
import time
from collections import defaultdict

last_request_time = defaultdict(float)
visited_content_hashes = set()
politeness_delay = 0.5 #seconds
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
    
    # Check robots.txt file
    robots_value = find_robotsfile(url)
    if(robots_value == False):
        printf("[SCRAPER] Skipping {url} because not allowed by robots.txt")
        return []
    elif(robots_value == True):
        # Use default politeness delay
        time.sleep(politeness_delay)
    elif(isinstance(robots_value, int) or isinstance(robots_value, float)):
        # Use robots politeness delay
        time.sleep(robots_value)
    
    # Check if page is valuable (text-rich, non-duplicate, reasonable size)
    if not resp.raw_response or resp.status != 200:
        return []


    content = resp.raw_response.content
    if len(content) == 0:
        printf("[SCRAPER] Skipping {url} because no content")
        return []

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

def find_robotsfile(url):
    """
    Parses through the robots.txt file of a url; returns False if not allowed to parse by robots.txt, True if 
    allowed but no crawl delay, or the crawl delay value
    """
    parsed = urlparse(url)
    domain = parsed.scheme + "://" + parsed.netloc
    robot_domain = domain + "/robots.txt"
    robot_parser = my_robot.RobotFileParser()
    robot_parser.set_url(robot_domain)
    robot_parser.read()
    if (robot_parser.can_fetch("*", domain)):
        print("Allowed to scrape by robots.txt")
        crawl_delay = robot_parser.crawl_delay("*")
        if (crawl_delay):
            return crawl_delay
        else:
            return True
    else:
        return False

def normalize_url(url):
    parsed = urlparse(url)
    clean_path = re.sub(r"/+", "/", parsed.path)  # remove multiple slashes
    if (clean_path != "/" and clean_path.endswith("/")): # remove ending slash
        clean_path = clean_path[:-1]
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

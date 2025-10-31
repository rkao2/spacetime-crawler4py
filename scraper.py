import re
from urllib.parse import urljoin, urldefrag, urlparse, parse_qsl
import urllib.robotparser as my_robot
from bs4 import BeautifulSoup
import time
import hashlib
from collections import defaultdict

last_request_time = defaultdict(float)
visited_content_hashes = set()

# MIN_TEXT_LENGTH = 200  # minimum text length to consider page valuable
# MAX_HTML_SIZE = 2_000_000  # max page size in bytes (2MB)
politeness_delay = 0.5

visited_urls = set()
last_crawl_time = {}

# ALLOWED_DOMAINS = ("ics.uci.edu", "cs.uci.edu", "informatics.uci.edu", "stat.uci.edu")

def scraper(url, resp):

    global visited_urls
    url = normalize_url(url)
    
    # already visited
    if url in visited_urls:
        print(f"[SCRAPER] Skipping already visited: {url}")
        return []
    visited_urls.add(url)

    # politeness per domain
    domain = urlparse(url).netloc
    last_time = last_request_time.get(domain, 0)
    elapsed = time.time() - last_time
    if elapsed < politeness_delay:
        time.sleep(politeness_delay - elapsed)
    last_request_time[domain] = time.time()


    
    # Check robots.txt file
    robots_value = find_robotsfile(url)
    if(robots_value == False):
        print(f"[SCRAPER] Skipping {url} because not allowed by robots.txt")
        return []
    elif(robots_value == True):
        # Use default politeness delay
        time.sleep(politeness_delay)
    elif(isinstance(robots_value, int) or isinstance(robots_value, float)):
        # Use robots politeness delay
        print(f"Crawl delay {robots_value}")
        time.sleep(robots_value)
    
    # Check if page is valuable (text-rich, non-duplicate, reasonable size)
    if not resp.raw_response or resp.status != 200:
        return []

    
    content = resp.raw_response.content

    """
    if len(content) > MAX_HTML_SIZE:
        print(f"[SCRAPER] Skipping {url} because it is too large")
        return []

    """
    
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
    valid_links = [link for link in links if is_valid(link)]
    visited_urls.add(url)

    print(f"[SCRAPER] Returning {len(valid_links)} new links from {url}")
    return valid_links
    #return [link for link in links if is_valid(link) and link not in visited_urls]
    


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
    try:
        robot_parser.read()
    except:
        print("ERROR reading robot txt")
        return True
    
    """
    if (robot_parser.can_fetch("*", domain)):
        print("Allowed to scrape by robots.txt")
        crawl_delay = robot_parser.crawl_delay("*")
        print(f"Crawl delay {crawl_delay}")
        if (crawl_delay is not None):
            return crawl_delay
        else:
            return True
    else:
        return False
    """

    can_fetch = robot_parser.can_fetch("*", url)
    if not can_fetch:
        return False

    crawl_delay = robot_parser.crawl_delay("*")
    if crawl_delay is not None:
        return crawl_delay
    return True
    

def normalize_url(url):
    try:
        parsed = urlparse(url)
        clean_path = re.sub(r"/+", "/", parsed.path)  # remove multiple slashes

        #check if ends in zip file
        if(url.lower().endswith(".zip")):
            return None
        
        # Clean query parameters
        query_pairs = parse_qsl(parsed.query)
        query_list = []
        for key, value in query_pairs:
            if re.match(r"(utm_|sessionid|ref|fbclid|PHPSESSID)", key):
                continue
            if key in {"ns", "media", "image", "do"}:
                continue
            query_list.append(f"{key}={value}")
        clean_query = "&".join(query_list)


        normalized = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            path=clean_path,
            query=clean_query,
            fragment=""  # drop fragment
        )
        return normalized.geturl()
    except Exception:
        return None

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
        if normalized and is_valid(normalized):
            links.add(normalized)

    print(f"[SCRAPER] Extracted {len(links)} links from {url}")

    return list(links)

def is_valid(url):
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        
        # Check allowed domains
        allowed_domains = (
            "ics.uci.edu",
            "cs.uci.edu",
            "informatics.uci.edu",
            "stat.uci.edu",
        )

        # Filter out the calendar trap 
        if not any(domain in parsed.netloc for domain in allowed_domains):
            return False
        
        # Filter out non-HTML resources
        if re.search(r"(page|offset|start|p)=\d{2,}", parsed.query.lower()):
            return False

        if "calendar" in parsed.path or "event" in parsed.path:
            return False

        return True

    except TypeError:
        # print("TypeError for ", url)
        return False

import re
from urllib.parse import urljoin, urldefrag, urlparse, parse_qsl
import urllib.robotparser as my_robot
from bs4 import BeautifulSoup
import time
import hashlib
import string
from collections import defaultdict

last_request_time = defaultdict(float)
visited_content_hashes = set()
# POLITENESS_DELAY = 2  # seconds
# MIN_TEXT_LENGTH = 200  # minimum text length to consider page valuable
MAX_HTML_SIZE = 2_000_000  # max page size in bytes (2MB)
politeness_delay = 0.5

visited_urls = set()
last_crawl_time = {}

# ALLOWED_DOMAINS = ("ics.uci.edu", "cs.uci.edu", "informatics.uci.edu", "stat.uci.edu")

def scraper(url, resp):
    depth = url[1]
    url = url[0]
    
    global visited_urls
    url = normalize_url(url)
    if not url:
        print(f"[SCRAPER] Skipping because not supported file type")
        return []
    if url in visited_urls:
        print(f"[SCRAPER] Skipping already visited: {url}")
        return []
    
    
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
    
    print(f"after sleep here")
    # Check if page is valuable (text-rich, non-duplicate, reasonable size)
    if not resp.raw_response or resp.status != 200:
        return []
    visited_urls.add(url)
    print(f"RESPONSE IS {resp.raw_response}")
    content = resp.raw_response.content
    if len(content) > MAX_HTML_SIZE:
        print(f"[SCRAPER] Skipping {url} because it is too large")
        return []
    if len(content) == 0:
        print(f"[SCRAPER] Skipping {url} because no content!")
        return []

    soup = BeautifulSoup(content, "html.parser")
    # text = soup.get_text(strip=True)
    text = soup.get_text()
    translator = str.maketrans('', '', string.punctuation)
    cleaned_text = text.translate(translator)
    
    words = cleaned_text.split()
    print("LEN OF WORDS IN PAGE IS ", len(words))
    # for word in words:
    #     print("WORD FROM PAGE: ", word, "\n")
    # print("TEXT FROM SOUP ", text)
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
    return [(link, depth) for link in links if is_valid(link) and link not in visited_urls]


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
    try:
        robot_parser.read()
    except:
        print("ERROR reading robot txt")
        return True
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

def normalize_url(url):
    parsed = urlparse(url)
    clean_path = re.sub(r"/+", "/", parsed.path)  # remove multiple slashes
    query_pairs = parse_qsl(parsed.query)
    list_query = []

    #check if ends in zip file
    if re.search(r"\.(ps\.Z|ps|pdf|zip|tar\.gz|py|exe|jpg|png|gif|mp4)$", parsed.path, re.IGNORECASE):
        return None
    # if(url.lower().endswith(".zip")):
    #     return None
    
    # potential queries to skip "tab", "tab_files", "tab_details", "tab_history", 
    for key, value in query_pairs:
        if(re.search(r"(utm_|sessionid|ref|fbclid|PHPSESSID|tribe__ecp|ical|tribe-bar)", key)):
            continue
        if(key in {"ns", "media", "image", "do"}):
            continue
        key_val = "=".join([key,value])
        list_query.append(key_val)
    clean_query = "&".join(list_query)


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
        try: 
            joined = urljoin(url, href)
            normalized = normalize_url(joined)
            if normalized and is_valid(normalized):
                links.add(normalized)
        except ValueError:
            continue

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
        list_of_domains = ["ics.uci.edu","cs.uci.edu", "informatics.uci.edu", "stat.uci.edu"]
        found = False
        for domain in list_of_domains:
            if domain in parsed.netloc:
                found = True
        if not found:
            return False
        
        # Filter out non-HTML resources
        if re.search(r"(page|offset|start|p)=\d{2,}", parsed.query.lower()):
            return False

        return True

    except TypeError:
        print("TypeError for ", url)
        return False

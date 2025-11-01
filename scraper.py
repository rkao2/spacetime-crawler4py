import re
from urllib.parse import urljoin, urldefrag, urlparse, parse_qsl
from bs4 import BeautifulSoup
import time
import hashlib
import string
import threading
from collections import defaultdict, Counter
import nltk
from nltk.corpus import stopwords

last_request_time = defaultdict(float)
visited_content_hashes = set()
word_freq = Counter()
ics_subdomains = defaultdict(set)

# MIN_TEXT_LENGTH = 200  # minimum text length to consider page valuable
MAX_HTML_SIZE = 2_000_000  # max page size in bytes (2MB)
politeness_delay = 0.5

longest_url = None
longest_wordcount = 0
visited_urls = set()
last_crawl_time = {}
visited_urls_lock = threading.RLock() 
visited_content_lock = threading.RLock()

longest_lock = threading.RLock()
word_freq_lock = threading.RLock()
nltk.download('stopwords')
english_stopwords = set(stopwords.words('english'))


# ALLOWED_DOMAINS = ("ics.uci.edu", "cs.uci.edu", "informatics.uci.edu", "stat.uci.edu")

def scraper(url, resp):
    global visited_urls
    global longest_wordcount, longest_url
    depth = url[1]
    url = url[0]

    if resp is None or not hasattr(resp, 'raw_response') or resp.raw_response is None:
        print(f"[SCRAPER] No response for {url}")
        return []

    if resp.status != 200:
        print(f"[SCRAPER] Skipping {url}, status {resp.status}")
        return []

    global visited_urls
    url = normalize_url(url)
    if not url:
        print(f"[SCRAPER] Skipping unsupported file type")
        return []

    with visited_urls_lock:
        if url in visited_urls:
            print(f"[SCRAPER] Skipping already visited: {url}")
            return []
        visited_urls.add(url)

    content = resp.raw_response.content
    if len(content) == 0 or len(content) > MAX_HTML_SIZE:
        print(f"[SCRAPER] Skipping {url} due to size")
        return []
    
    time.sleep(politeness_delay)
    soup = BeautifulSoup(content, "html.parser")
    text = soup.get_text()
    translator = str.maketrans('', '', string.punctuation)
    cleaned_text = text.translate(translator)
    words = [w.lower() for w in cleaned_text.split() if w]

    #checking duplicate content
    content_hash = hashlib.md5(cleaned_text.encode("utf-8")).hexdigest()
    with visited_content_lock:
        if content_hash in visited_content_hashes:
            print(f"[SCRAPER] Duplicate content: {url}")
            return []
        visited_content_hashes.add(content_hash)

    
    # report 
    page_wordcount = 0
    with word_freq_lock:
        for w in words:
            if w in english_stopwords:
                continue
            if len(w) == 1:
                continue
            word_freq[w] += 1
            page_wordcount += 1

    with longest_lock:
        if page_wordcount > longest_wordcount:
            longest_wordcount = page_wordcount
            longest_url = url

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.endswith("ics.uci.edu"):
        ics_subdomains[host].add(url)
    
    print(f"[Scraper] {url} had {page_wordcount} non-stopwords")

    links = extract_next_links(url, resp)
    return [(link, depth + 1) for link in links if is_valid(link)]


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
        

        list_of_domains = ["ics.uci.edu","cs.uci.edu", "informatics.uci.edu", "stat.uci.edu"]
        found = False
        for domain in list_of_domains:
            if domain in parsed.netloc:
                found = True
        if not found:
            return False
        

        if "wics.ics.uci.edu" in parsed.netloc and (
            "calendar" in parsed.path
            or "event" in parsed.path
            or "eventdate" in parsed.query
            or "month" in parsed.query
            or "day" in parsed.query
            or "year" in parsed.query
        ):
            return False
        
        if "isg.ics.uci.edu" in parsed.netloc and "/events/" in parsed.path:
            return False
        
        if "doku" in parsed.netloc or "doku" in parsed.path:
            return False
        
        # filtering out grape commits
        if "grape.ics.uci.edu" in parsed.netloc:
            if "version=" in parsed.query or "action=diff" in parsed.query:
                return False


        if "gitlab.ics.uci.edu" in parsed.netloc:

            if re.search(r"/-/commit|/-/tree|/-/blob|/-/merge_requests|/-/issues", parsed.path):
                return False

            if any(param in parsed.query for param in ["view=", "action=", "controller=", "id="]):
                return False
            
            if re.search(r"[a-f0-9]{20,}", parsed.path):
                return False
            
            if parsed.path.count("/") > 4:
                return False

            return True
        
        # Filter out non-HTML resources
        if re.search(r"(page|offset|start|p)=\d{2,}", parsed.query.lower()):
            return False

        return True

    except TypeError:
        print("TypeError for ", url)
        return False
    

#Report helpers
def get_top_50():
    return word_freq.most_common(50)

def get_longest_page():
    return longest_url, longest_wordcount

def get_ics_subdomain_report():
    results = []
    for subdomain, urls in ics_subdomains.items():
        results.append((subdomain, len(urls)))
    results.sort(key=lambda x: x[0])
    return results

def crawl_report():
    print("CRAWL REPORT:")
    print("Total pages crawled:", len(visited_urls))

    lp_url, lp_wc = get_longest_page()
    print(f"Longest page: {lp_url}")
    print("Word count on longest page", lp_wc)

    print("\nTop 50 words:")
    for w, c in get_top_50():
        print(f"{w}: {c}")
    
    print("\nICS subdomains:")
    for sub, cnt in get_ics_subdomain_report():
        print(f"{sub}, {cnt}")

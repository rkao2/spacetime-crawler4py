import re
from urllib.parse import urljoin, urldefrag, urlparse
from bs4 import BeautifulSoup


# ALLOWED_DOMAINS = ("ics.uci.edu", "cs.uci.edu", "informatics.uci.edu", "stat.uci.edu")

def scraper(url, resp):
    links = extract_next_links(url, resp)
    return [link for link in links if is_valid(link)]


 # resp.url: the actual url of the page
    # resp.status: the status code returned by the server. 200 is OK, you got the page. Other numbers mean that there was some kind of problem.
    # resp.error: when status is not 200, you can check the error here, if needed.
    # resp.raw_response: this is where the page actually is. More specifically, the raw_response has two parts:
    #         resp.raw_response.url: the url, again
    #         resp.raw_response.content: the content of the page!
    # Return a list with the hyperlinks (as strings) scrapped from resp.raw_response.content
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
        if is_valid(joined):
            links.add(joined)

    print(f"[SCRAPER] Extracted {len(links)} links from {url}")

    return list(links)

def is_valid(url):
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        
        # Check allowed domains
        if "uci.edu" not in parsed.netloc:
            return False
        
        # Filter out non-HTML resources
        if re.search(
            r"\.(jpg|jpeg|png|gif|css|js|pdf|zip|mp4|mp3|avi|mov|wmv|tar|gz|dmg|exe|ico)$",
            parsed.path.lower(),
        ):
            return False

        return True

    except TypeError:
        print("TypeError for ", url)
        return False

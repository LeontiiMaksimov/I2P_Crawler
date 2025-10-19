import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
import os
import time
from collections import deque
import base64
import hashlib

I2P_PROXY = {
    'http': 'http://127.0.0.1:4444',
    'https': 'http://127.0.0.1:4444'
}

START_URL = "http://identiguy.i2p"

MAX_DEPTH = 5

PHONEBOOK_FILE = "phonebook.txt"
VISITED_FILE = "visited.txt"
QUEUE_FILE = "queue.txt"  
ONIONS_FILE = "onions.txt"
CLEARWEB_FILE = "clearweb.txt"

def load_from_file(filename):
    if not os.path.exists(filename):
        print(f"[INFO] File {filename} does not exist. Starting with empty set.")
        return set()
    print(f"[INFO] Loading from {filename}...")
    with open(filename, 'r', encoding='utf-8') as f:
        data = set(line.strip() for line in f if line.strip())
    print(f"[INFO] Loaded {len(data)} entries from {filename}.")
    return data

def append_to_file(filename, data):
    with open(filename, 'a', encoding='utf-8') as f:
        f.write(data + '\n')
    print(f"[INFO] Appended to {filename}: {data}")

def save_queue(queue):
    with open(QUEUE_FILE, 'w', encoding='utf-8') as f:
        for url, depth in queue:
            f.write(f"{url}|{depth}\n")
    print(f"[INFO] Saved queue to {QUEUE_FILE}. Current queue size: {len(queue)}")

def load_queue():
    if not os.path.exists(QUEUE_FILE):
        print(f"[INFO] Queue file {QUEUE_FILE} does not exist. Starting with empty queue.")
        return deque()
    print(f"[INFO] Loading queue from {QUEUE_FILE}...")
    queue = deque()
    with open(QUEUE_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                url, depth = line.strip().split('|')
                queue.append((url, int(depth)))
    print(f"[INFO] Loaded queue with {len(queue)} URLs.")
    return queue

def normalize_i2p_url(url):
    parsed = urlparse(url)
    if '.i2p' not in parsed.netloc:
        return url  
    query_params = parse_qs(parsed.query)
    if 'i2paddresshelper' in query_params:
        helper = query_params['i2paddresshelper'][0]
        try:
            dest_bytes = base64.b64decode(helper)
            hash_digest = hashlib.sha256(dest_bytes).digest()
            b32_hash = base64.b32encode(hash_digest).decode('utf-8').lower().rstrip('=')
            new_netloc = f"{b32_hash}.b32.i2p"
            normalized = parsed._replace(netloc=new_netloc, query='').geturl()
            print(f"[INFO] Normalized I2P URL: {url} -> {normalized}")
            return normalized
        except Exception as e:
            print(f"[WARN] Failed to normalize {url}: {e}. Using original.")
            return url
    return url

def clean_url(url):
    parsed = urlparse(url)
    clean = parsed._replace(fragment="").geturl()
    if '.i2p' in parsed.netloc:
        return normalize_i2p_url(clean)
    return clean

def main():
    print("--- I2P BFS Web Crawler ---")
    print(f"Starting URL: {START_URL}")
    print(f"Using proxy: {I2P_PROXY}")
    print(f"Max depth: {MAX_DEPTH if MAX_DEPTH > 0 else 'unlimited'}")
    print("Ensure your I2P router is running and fully bootstrapped.\n")

    visited_urls = load_from_file(VISITED_FILE)
    phonebook_links = load_from_file(PHONEBOOK_FILE)
    onions_links = load_from_file(ONIONS_FILE)
    clearweb_links = load_from_file(CLEARWEB_FILE)

    queue = load_queue()
    if not queue and START_URL not in visited_urls:
        print(f"[INFO] Queue is empty and start URL not visited. Adding: {START_URL} at depth 0")
        queue.append((START_URL, 0))
        save_queue(queue)  

    while queue:
        current_url, current_depth = queue.popleft()
        print(f"[INFO] Popped from queue: {current_url} (depth {current_depth}). Queue remaining: {len(queue)}")
        save_queue(queue)

        if current_url in visited_urls:
            print(f"[INFO] Skipping already visited: {current_url}")
            continue

        print(f"[*] Crawling: {current_url} (depth {current_depth})")

        response = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"[INFO] Attempt {attempt + 1}/{max_retries}: Connecting to {current_url} via proxy {I2P_PROXY}")
                response = requests.get(current_url, proxies=I2P_PROXY, timeout=240)
                response.raise_for_status()  
                print(f"[INFO] Connection successful on attempt {attempt + 1}")
                break
            except requests.exceptions.RequestException as e:
                print(f" [!] Attempt {attempt + 1}/{max_retries} FAILED for {current_url}. Error: {e}")
                if attempt + 1 < max_retries:
                    sleep_time = 5 * (attempt + 1)
                    print(f"[INFO] Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    print(f" [!] Max retries reached. Giving up on {current_url}.")

        if response is None:
            print(f"[WARN] Failed to fetch {current_url} after all retries. Not marking as visited (will retry next run).")
            continue

        print(f" [+] Success! Status: {response.status_code}. Content length: {len(response.text)} bytes. Parsing for links...")

        visited_urls.add(current_url)
        append_to_file(VISITED_FILE, current_url)

        parsed_current = urlparse(current_url)
        if ".i2p" in parsed_current.netloc.lower() and current_url not in phonebook_links:
            print(f"[INFO] Adding live I2P site to phonebook: {current_url}")
            phonebook_links.add(current_url)
            append_to_file(PHONEBOOK_FILE, current_url)

        soup = BeautifulSoup(response.text, 'html.parser')

        i2p_links_found = 0
        onions_found = 0
        clearweb_found = 0
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']

            absolute_url = urljoin(current_url, href)

            normalized_url = clean_url(absolute_url)
            parsed_url = urlparse(normalized_url)
            netloc = parsed_url.netloc.lower()

            if ".i2p" in netloc:
                i2p_links_found += 1  

                new_depth = current_depth + 1
                if MAX_DEPTH > 0 and new_depth > MAX_DEPTH:
                    print(f"[INFO] Skipping add to queue for {normalized_url}: Depth {new_depth} exceeds MAX_DEPTH {MAX_DEPTH}")
                    continue
                if normalized_url not in visited_urls and not any(q_url == normalized_url for q_url, _ in queue):
                    print(f"[INFO] Adding to queue: {normalized_url} at depth {new_depth}")
                    queue.append((normalized_url, new_depth))
            elif ".onion" in netloc:
                if normalized_url not in onions_links:
                    onions_found += 1
                    print(f"[INFO] New onion entry found: {normalized_url}")
                    onions_links.add(normalized_url)
                    append_to_file(ONIONS_FILE, normalized_url)
            else:
                if normalized_url not in clearweb_links:
                    clearweb_found += 1
                    print(f"[INFO] New clearweb entry found: {normalized_url}")
                    clearweb_links.add(normalized_url)
                    append_to_file(CLEARWEB_FILE, normalized_url)

        save_queue(queue)
        print(f" [>] Found and processed {i2p_links_found} new .i2p links, {onions_found} new .onion links, {clearweb_found} new clearweb links. Queue now: {len(queue)}")

        print("[INFO] Sleeping 1 second before next request...")
        time.sleep(1)

    if phonebook_links:
        phonebook_list = sorted(phonebook_links)
        with open(PHONEBOOK_FILE, 'w', encoding='utf-8') as f:
            for url in phonebook_list:
                f.write(url + '\n')
        print(f"[INFO] Sorted and rewrote {PHONEBOOK_FILE} with {len(phonebook_list)} unique entries.")

    if onions_links:
        onions_list = sorted(onions_links)
        with open(ONIONS_FILE, 'w', encoding='utf-8') as f:
            for url in onions_list:
                f.write(url + '\n')
        print(f"[INFO] Sorted and rewrote {ONIONS_FILE} with {len(onions_list)} unique entries.")

    if clearweb_links:
        clearweb_list = sorted(clearweb_links)
        with open(CLEARWEB_FILE, 'w', encoding='utf-8') as f:
            for url in clearweb_list:
                f.write(url + '\n')
        print(f"[INFO] Sorted and rewrote {CLEARWEB_FILE} with {len(clearweb_list)} unique entries.")

    print("\n--- Crawl Complete ---")
    print("The queue is empty. Run the script again to resume if new links are added or to retry failed ones.")

if __name__ == "__main__":
    main()

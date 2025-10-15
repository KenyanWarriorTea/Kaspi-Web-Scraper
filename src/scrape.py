#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Kaspi Web Scraper 
Simple, modular scraper that:
- fetches listing pages
- extracts product cards (name, price, link)
- optionally fetches product page specs
- saves results to JSON and/or CSV

Usage:
    python src/scrape.py --url "https://kaspi.kz/shop/c/notebooks/" --pages 3 --output kaspi.json --format json
"""

import argparse
import csv
import json
import logging
import random
import sys
import time
from typing import List, Dict, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException, HTTPError, ConnectionError, Timeout
from urllib3.util.retry import Retry

# -----------------------
# Configuration & utils
# -----------------------

USER_AGENTS = [
    # common user agents; you can expand this list
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
]

DEFAULT_TIMEOUT = 15  # seconds

logger = logging.getLogger("kaspi_scraper")


def create_session(timeout: int = DEFAULT_TIMEOUT, retries: int = 3, backoff_factor: float = 0.3) -> requests.Session:
    """
    Create a requests.Session with retry strategy and a rotating user-agent header.
    """
    s = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"])
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    # initial headers - user agent will be randomized before each request
    s.headers.update({"Accept-Language": "en-US,en;q=0.9"})
    s.request_timeout = timeout  # custom attribute
    return s


def safe_get(session: requests.Session, url: str, timeout: Optional[int] = None) -> Optional[requests.Response]:
    """
    GET wrapper with randomized user-agent and handled exceptions.
    Returns Response or None.
    """
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        response = session.get(url, headers=headers, timeout=timeout or session.request_timeout)
        response.raise_for_status()
        return response
    except (HTTPError, ConnectionError, Timeout, RequestException) as e:
        logger.debug("Request failed for %s: %s", url, e)
        return None


# -----------------------
# Parsers
# -----------------------

def parse_listing_page(html: str, base_url: str) -> List[Dict]:
    """
    Parse product cards from a listing page.
    Returns list of dicts with keys: name, price_raw, link.
    """
    soup = BeautifulSoup(html, "html.parser")

    results = []
    # Generic selectors based on Kaspi page structure; may need adjustment over time
    product_cards = soup.select(".item-card") or soup.select(".product-card") or soup.select(".product")
    for card in product_cards:
        try:
            name_el = card.select_one(".item-card__name") or card.select_one(".product-name") or card.select_one("a")
            price_el = card.select_one(".item-card__prices-price") or card.select_one(".price") or card.select_one(".product-price")
            link_el = card.select_one("a") or card.select_one(".item-card__name-link")

            if not name_el or not price_el or not link_el:
                continue

            name = name_el.get_text(strip=True)
            price_raw = price_el.get_text(strip=True).replace('\xa0', ' ').strip()
            href = link_el.get("href", "")
            link = urljoin(base_url, href) if href else ""

            results.append({
                "name": name,
                "price_raw": price_raw,
                "link": link
            })
        except Exception as e:
            logger.debug("Failed to parse a card: %s", e)
            continue

    return results


def parse_product_page(html: str) -> Dict:
    """
    Parse a product detail page and return a dictionary of specifications.
    Extracts elements from .specifications-list__el or generic dt/dd pairs.
    """
    soup = BeautifulSoup(html, "html.parser")
    specs = {}

    # Try Kaspi-specific structure first
    spec_items = soup.select(".specifications-list__el") or []
    if spec_items:
        for el in spec_items:
            dt = el.select_one("dt")
            dd = el.select_one("dd")
            if dt and dd:
                key = dt.get_text(strip=True)
                val = dd.get_text(strip=True)
                specs[key] = val
        return specs

    # Fallback: parse dt / dd pairs if present
    dt_elements = soup.select("dt")
    dd_elements = soup.select("dd")
    if dt_elements and dd_elements and len(dt_elements) == len(dd_elements):
        for dt, dd in zip(dt_elements, dd_elements):
            key = dt.get_text(strip=True)
            val = dd.get_text(strip=True)
            specs[key] = val
        return specs

    # As last fallback: parse simple key:value lines
    info_blocks = soup.select(".product-specs") or soup.select(".specs")
    for block in info_blocks:
        text = block.get_text(separator="\n").strip()
        for line in text.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                specs[k.strip()] = v.strip()
    return specs


# -----------------------
# Exporters
# -----------------------

def save_csv(path: str, items: List[Dict], fieldnames: Optional[List[str]] = None):
    if not items:
        logger.info("No items to write to CSV.")
        return
    if fieldnames is None:
        # collect union of keys
        keys = set()
        for it in items:
            keys.update(it.keys())
        fieldnames = list(keys)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for it in items:
            writer.writerow(it)
    logger.info("Saved %d records to CSV: %s", len(items), path)


def save_json(path: str, items: List[Dict]):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    logger.info("Saved %d records to JSON: %s", len(items), path)


# -----------------------
# Main scraping workflow
# -----------------------

def scrape_listing(session: requests.Session, base_url: str, pages: int = 1,
                   delay_min: float = 1.0, delay_max: float = 3.0,
                   fetch_product_pages: bool = False) -> List[Dict]:
    """
    Scrape `pages` pages starting from base_url. If the site uses "page" param, it will try to append /pN or add ?page=N.
    This function is conservative about constructing next page URLs; some sites require custom logic.
    """
    items = []
    current_url = base_url.rstrip("/")
    for page in range(1, pages + 1):
        # try a few common pagination patterns
        candidate_urls = [
            current_url if page == 1 else f"{current_url}/page/{page}",
            current_url if page == 1 else f"{current_url}?page={page}",
            current_url if page == 1 else f"{current_url}/p{page}"
        ]
        page_html = None
        for url in candidate_urls:
            logger.info("Fetching listing page: %s", url)
            resp = safe_get(session, url)
            if resp and resp.status_code == 200:
                page_html = resp.text
                current_page_url = url
                break
            time.sleep(random.uniform(delay_min, delay_max))

        if not page_html:
            logger.warning("Failed to fetch listing page %d (tried patterns). Stopping.", page)
            break

        parsed = parse_listing_page(page_html, base_url)
        logger.info("Found %d product cards on page %d", len(parsed), page)
        for p in parsed:
            entry = {
                "name": p.get("name"),
                "price_raw": p.get("price_raw"),
                "link": p.get("link")
            }
            if fetch_product_pages and entry["link"]:
                time.sleep(random.uniform(delay_min, delay_max))
                logger.debug("Fetching product page: %s", entry["link"])
                prod_resp = safe_get(session, entry["link"])
                if prod_resp:
                    specs = parse_product_page(prod_resp.text)
                    entry["specs"] = specs
                else:
                    entry["specs"] = {}
            items.append(entry)

        # polite delay between listing pages
        time.sleep(random.uniform(delay_min, delay_max))

    return items


def build_argparser():
    p = argparse.ArgumentParser(description="Kaspi Web Scraper")
    p.add_argument("--url", "-u", required=True, help="Base listing URL (category) to scrape")
    p.add_argument("--pages", "-p", type=int, default=1, help="Number of listing pages to scrape")
    p.add_argument("--delay-min", type=float, default=1.0, help="Minimum delay between requests (seconds)")
    p.add_argument("--delay-max", type=float, default=3.0, help="Maximum delay between requests (seconds)")
    p.add_argument("--output", "-o", default="kaspi_output.json", help="Output filename (json or csv)")
    p.add_argument("--format", "-f", choices=["json", "csv", "both"], default="json", help="Output format")
    p.add_argument("--fetch-products", action="store_true", help="Also fetch product detail pages for specs")
    p.add_argument("--retries", type=int, default=3, help="Number of request retries")
    return p


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = build_argparser().parse_args()

    # minor validation
    if args.delay_min < 0 or args.delay_max < 0 or args.delay_min > args.delay_max:
        logger.error("Invalid delay range")
        sys.exit(2)

    # session
    session = create_session(retries=args.retries)

    logger.info("Starting scraper: url=%s pages=%d", args.url, args.pages)
    items = scrape_listing(
        session=session,
        base_url=args.url,
        pages=args.pages,
        delay_min=args.delay_min,
        delay_max=args.delay_max,
        fetch_product_pages=args.fetch_products
    )

    if not items:
        logger.info("No items scraped. Exiting.")
        return

    out = args.output
    fmt = args.format
    if fmt in ("json", "both"):
        json_path = out if out.lower().endswith(".json") or fmt == "json" else out.rsplit(".", 1)[0] + ".json"
        save_json(json_path, items)
    if fmt in ("csv", "both"):
        csv_path = out if out.lower().endswith(".csv") or fmt == "csv" else out.rsplit(".", 1)[0] + ".csv"
        # determine consistent field order
        fieldnames = ["name", "price_raw", "link", "specs"]
        save_csv(csv_path, items, fieldnames=fieldnames)

    logger.info("Done. Total items: %d", len(items))


if __name__ == "__main__":
    main()

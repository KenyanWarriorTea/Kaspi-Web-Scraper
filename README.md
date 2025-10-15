Kaspi Web Scraper

A web scraping script designed to collect product data from the Kaspi.kz marketplace. This tool extracts information such as product name, price, and availability, and saves it in a structured format for further analysis or automation workflows.

Features

Scrapes product data from Kaspi.kz

Extracts name, price, and availability status

Saves results locally in JSON/CSV format

Includes basic error handling for missing or blocked data

Lightweight and easy to modify for custom parsing targets

Tech Stack

Language: Python

Libraries Used: requests, BeautifulSoup4, json or csv

Output Format: JSON or CSV

Installation
git clone https://github.com/Lucky-Boo/kaspi-web-scraper.git
cd kaspi-web-scraper
pip install -r requirements.txt

Usage
python scrape.py


By default, the script scrapes predefined URLs from Kaspi.kz. You can modify the TARGET_URLS list inside scrape.py to set your own product links.

Example Output
[
  {
    "name": "Product Name",
    "price": "199 990 ₸",
    "availability": "In stock"
  }
]

Possible Improvements

Add multi-threading for faster scraping

Export to database (SQLite or PostgreSQL)

Implement proxy rotation to avoid request blocking

Add CLI arguments for dynamic URL input

License

Distributed under the MIT License. See LICENSE for more information.

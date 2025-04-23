import json
import os
from pathlib import Path
import random
import time
from typing import List
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
import tqdm
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def create_driver():
    # Set up Chrome options for headless mode
    options = Options()
    options.add_argument("--headless=new")  # Use new headless mode
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36")

    # Initialize the WebDriver
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


def get_ad_ids(driver, url):
    # Navigate to the FINN.no car search page
    driver.get(url)

    # Wait until the ad elements are present
    wait = WebDriverWait(driver, 10)
    try:
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.sf-search-ad-link")))
    except TimeoutException:
        return []

    # Find all ad elements
    ad_elements = driver.find_elements(By.CSS_SELECTOR, "a.sf-search-ad-link")

    # Extract ad IDs
    ad_ids = [
        ad.get_attribute("id")
        for ad in ad_elements
    ]

    return ad_ids


def find_all_ad_ids(driver, base_url) -> List[str]:
    results = get_ad_ids(driver, base_url)
    if (len(results) == 0):
        return results

    for i in tqdm.tqdm(range(2, 100)):
        time.sleep(random.randint(1000, 3000) / 1000)
        more = get_ad_ids(driver, base_url + f"&page={i}")
        if (len(more) == 0):
            break
        results += more
    return list(dict.fromkeys(results).keys())


def main():
    # Set the base URL for the car search page on FINN.no
    u = "https://www.finn.no/mobility/search/car?model=1.818.7651"
    d = create_driver()
    try:
        ids = find_all_ad_ids(d, u)
        p = Path("data/ids.json")
        if p.exists():
            current = json.load(open("data/ids.json", "r"))
        else:
            current = []
        current.append({
            "url": u,
            "ids": ids,
            "timestamp": time.time(),
        })
        json.dump(current, open("data/ids.json", "w"), indent=2)
    finally:
        d.quit()


if __name__ == "__main__":
    main()

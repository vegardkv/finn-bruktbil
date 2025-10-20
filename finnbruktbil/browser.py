from __future__ import annotations

import random
import time
from typing import Iterable, Iterator

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


def create_driver(headless: bool = True) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
    )
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


def wait_for_elements(driver: webdriver.Chrome, selector: str, timeout: int = 10) -> bool:
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector)))
        return True
    except TimeoutException:
        return False


def extract_attribute_values(elements: Iterable, attribute: str) -> Iterator[str]:
    for element in elements:
        value = element.get_attribute(attribute)
        if value:
            yield value


def polite_delay(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
    duration = random.uniform(min_seconds, max_seconds)
    time.sleep(duration)

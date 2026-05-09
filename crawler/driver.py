"""Selenium WebDriver lifecycle. Single source of truth — no duplicate init_driver.

The legacy notebook had ``init_driver`` defined twice with subtly different
options. This module replaces both, plus a thread-safe pool so we don't reopen
Chrome for every URL (the main cause of OOM in Colab).

Selenium 4.43.0 ships with **Selenium Manager** (the built-in successor to the
external ``webdriver-manager`` package). It auto-discovers Chrome on the host
and downloads a matching Chrome-for-Testing + ChromeDriver pair when none is
found, so we no longer need a third-party resolver. ``Service()`` with no
arguments delegates the whole resolution to Selenium Manager.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from queue import Empty, Queue
from typing import Iterator

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .settings import CrawlerSettings, Selectors

log = logging.getLogger(__name__)


def build_driver(settings: CrawlerSettings) -> webdriver.Chrome:
    """Build a single configured Chrome WebDriver.

    Driver and (when missing) the browser itself are resolved by Selenium
    Manager — no external installer needed.
    """
    opts = Options()
    if settings.chrome_binary:
        # Pin a specific Chrome binary if the host has one (e.g. Colab's
        # /usr/bin/google-chrome). Otherwise let Selenium Manager fetch
        # Chrome-for-Testing on first launch.
        opts.binary_location = settings.chrome_binary
    if settings.headless:
        opts.add_argument("--headless=new")

    # Stability + speed in containerized / Colab environments
    for flag in (
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--disable-extensions",
        "--disable-setuid-sandbox",
        "--ignore-certificate-errors",
        "--disable-blink-features=AutomationControlled",
        "--blink-settings=imagesEnabled=false",   # ~30% faster page loads
        "--window-size=1920,1080",
        f"user-agent={settings.user_agent}",
    ):
        opts.add_argument(flag)

    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.page_load_strategy = "eager"  # don't wait for sub-resources

    # Empty Service() delegates browser/driver resolution to Selenium Manager.
    driver = webdriver.Chrome(service=Service(), options=opts)
    driver.set_page_load_timeout(settings.request_timeout * 2)
    return driver


def wait_for_listings(driver: webdriver.Chrome, timeout: int) -> None:
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, Selectors.VEHICLE_CARD_LINK))
    )


def scroll_to_bottom(driver: webdriver.Chrome, pause: float, max_rounds: int) -> None:
    """Trigger lazy-load by scrolling until height stops growing."""
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(max_rounds):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        WebDriverWait(driver, pause).until(lambda _d: True)  # short structured wait
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            return
        last_height = new_height


class DriverPool:
    """Thread-safe Selenium driver pool with lazy creation and clean shutdown.

    Usage::

        with DriverPool(settings, size=2) as pool:
            with pool.borrow() as driver:
                driver.get(url)
    """

    def __init__(self, settings: CrawlerSettings, size: int):
        self._settings = settings
        self._size = max(1, size)
        self._pool: "Queue[webdriver.Chrome]" = Queue()
        self._created: list[webdriver.Chrome] = []
        self._closed = False

    def __enter__(self) -> "DriverPool":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @contextmanager
    def borrow(self, timeout: float = 60.0) -> Iterator[webdriver.Chrome]:
        if self._closed:
            raise RuntimeError("DriverPool is closed")
        driver = self._acquire(timeout)
        try:
            yield driver
        finally:
            if not self._closed:
                self._pool.put(driver)

    def _acquire(self, timeout: float) -> webdriver.Chrome:
        try:
            return self._pool.get_nowait()
        except Empty:
            pass
        if len(self._created) < self._size:
            driver = build_driver(self._settings)
            self._created.append(driver)
            return driver
        return self._pool.get(timeout=timeout)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for driver in self._created:
            try:
                driver.quit()
            except Exception:  # noqa: BLE001 — best-effort cleanup
                log.warning("Error quitting a driver", exc_info=True)
        self._created.clear()

"""
Browser navigation core built on SeleniumBase UC mode.
Disconnects ChromeDriver during page load so Cloudflare can't fingerprint it,
and auto-clicks Turnstile when it appears.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from crawler.logging_setup import get_logger

log = get_logger(__name__)


def scroll_to_bottom(sb, pause: float = 0.3, max_rounds: int = 8) -> None:
    """Repeatedly scroll until page height stops growing. Safe on empty body."""
    try:
        if not sb.execute_script("return document.body !== null;"):
            return
        last = sb.execute_script("return document.body.scrollHeight;")
        for _ in range(max_rounds):
            sb.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            sb.sleep(pause)
            new = sb.execute_script("return document.body.scrollHeight;")
            if new == last:
                break
            last = new
    except Exception as e:
        log.warning("scroll_to_bottom error: %s", e)


def get_soup(
    sb,
    url: str,
    target_css: str = "body",
    scroll: bool = False,
) -> BeautifulSoup:
    """
    Navigate using uc_open_with_reconnect (no async, no event loop conflict).
    Auto-solves Cloudflare Turnstile if the page title indicates a challenge.
    """
    sb.uc_open_with_reconnect(url, reconnect_time=4)

    title = sb.get_title()
    if "Just a moment" in title or "Verifying" in title:
        try:
            log.info("Turnstile detected — solving...")
            sb.uc_gui_click_captcha()
            sb.sleep(6)  # cars.com needs grace period after challenge clears
            log.info("Turnstile solved")
        except Exception as e:
            log.warning("Captcha solve failed: %s", e)

    if target_css != "body":
        try:
            sb.wait_for_element(target_css, timeout=25)
        except Exception:
            pass

    if scroll:
        scroll_to_bottom(sb)

    return BeautifulSoup(sb.get_page_source(), "html.parser")

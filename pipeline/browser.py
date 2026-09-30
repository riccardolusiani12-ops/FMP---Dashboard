"""
Chrome via Selenium 4 per i metodi di ripiego (nessun selenium-wire).

selenium-wire non è installabile nel venv della dash (richiede blinker<1.8 e
pkg_resources), quindi le risposte di rete si leggono dai log "performance"
di Chrome + Network.getResponseBody via CDP.
"""

from __future__ import annotations


def create_driver(headless: bool = True, performance_log: bool = False):
    # Import locale: selenium serve solo per i ripieghi.
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    opts.add_argument("--window-size=1600,1000")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--lang=en-GB")
    opts.add_argument("--disable-notifications")
    if headless:
        opts.add_argument("--headless=new")
    if performance_log:
        opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(90)
    if performance_log:
        driver.execute_cdp_cmd("Network.enable", {})
    return driver

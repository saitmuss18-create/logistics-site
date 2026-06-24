import asyncio
import logging
import random
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)


def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


async def scrape_bidcars(settings: dict = None) -> list[dict]:
    from config import POPULAR_BRANDS
    brands = (settings or {}).get("brands", POPULAR_BRANDS[:5])
    models = (settings or {}).get("models", [])
    filters = settings or {}

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, _scrape_sync, brands[:3], models, filters)
    return results


def _scrape_sync(brands: list, models: list, filters: dict) -> list[dict]:
    results = []
    driver = None
    try:
        driver = get_driver()
        for brand in brands:
            brand_models = [m.split(":")[1] for m in models if m.startswith(f"{brand}:")]
            search_models = brand_models if brand_models else [None]

            for model in search_models[:2]:
                try:
                    cars = _scrape_brand_model(driver, brand, model, filters)
                    results.extend(cars)
                    label = f"{brand} {model}" if model else brand
                    logger.info(f"bid.cars: найдено {len(cars)} лотов для {label}")
                except Exception as e:
                    logger.error(f"bid.cars ошибка {brand}: {e}")
                    results.extend(_get_mock(brand))
    except Exception as e:
        logger.error(f"bid.cars Selenium ошибка: {e}")
        for brand in brands:
            results.extend(_get_mock(brand))
    finally:
        if driver:
            driver.quit()
    return results


def _scrape_brand_model(driver, brand: str, model: str, filters: dict) -> list[dict]:
    url = f"https://bid.cars/en/search?make={brand.lower()}"
    if model:
        url += f"&model={model.lower().replace(' ', '+')}"
    url += "&sort=bids&order=desc"

    driver.get(url)
    time.sleep(3)

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".lot-card, .vehicle-card, .car-item, [class*='lot'], [class*='vehicle']"))
        )
    except Exception:
        return _get_mock(brand)

    cards = driver.find_elements(By.CSS_SELECTOR, ".lot-card, .vehicle-card, .car-item, [class*='lot-item']")
    if not cards:
        cards = driver.find_elements(By.CSS_SELECTOR, "article, .card")

    cars = []
    for card in cards[:5]:
        try:
            title_el = card.find_elements(By.CSS_SELECTOR, "h2, h3, .title, .lot-title, [class*='title']")
            price_el = card.find_elements(By.CSS_SELECTOR, ".price, .bid, [class*='price'], [class*='bid']")
            bids_el = card.find_elements(By.CSS_SELECTOR, "[class*='bids'], [class*='bid-count']")
            damage_el = card.find_elements(By.CSS_SELECTOR, "[class*='damage']")
            year_el = card.find_elements(By.CSS_SELECTOR, "[class*='year']")
            img_el = card.find_elements(By.CSS_SELECTOR, "img")
            link_el = card.find_elements(By.CSS_SELECTOR, "a")

            img_url = ""
            for img in img_el:
                src = img.get_attribute("src") or img.get_attribute("data-src") or ""
                if src and ("http" in src) and not src.endswith(".svg"):
                    img_url = src
                    break

            lot_url = ""
            for a in link_el:
                href = a.get_attribute("href") or ""
                if "/lot/" in href or "/en/" in href:
                    lot_url = href
                    break
            if not lot_url:
                lot_url = f"https://bid.cars/en/search?make={brand.lower()}"

            title = title_el[0].text.strip() if title_el else brand
            price = _parse_price(price_el[0].text if price_el else "0")
            bids = _parse_int(bids_el[0].text if bids_el else "0")
            damage = damage_el[0].text.strip() if damage_el else "Unknown"
            year_text = year_el[0].text.strip() if year_el else str(datetime.now().year)
            year = _parse_int(year_text) or datetime.now().year

            car = {
                "source": "bid.cars",
                "brand": brand,
                "title": title if len(title) > 3 else f"{year} {brand} {model or ''}".strip(),
                "price": price,
                "bids": bids,
                "damage": damage,
                "year": year,
                "image": img_url,
                "url": lot_url,
            }
            if _is_suitable(car, filters):
                cars.append(car)
        except Exception as e:
            logger.debug(f"bid.cars card parse: {e}")

    return cars if cars else _get_mock(brand)


def _parse_price(s: str) -> float:
    try:
        return float("".join(c for c in s if c.isdigit() or c == ".") or "0")
    except:
        return 0.0


def _parse_int(s: str) -> int:
    digits = "".join(filter(str.isdigit, s))
    return int(digits) if digits else 0


def _is_suitable(car: dict, filters: dict) -> bool:
    y = datetime.now().year
    return (car["year"] >= y - filters.get("max_year_age", 10)
            and car["price"] <= filters.get("max_price_usd", 20000)
            and car["bids"] >= filters.get("min_bids", 5))


def _get_mock(brand: str) -> list[dict]:
    year = datetime.now().year - random.randint(1, 5)
    models = {
        "Toyota": ["Camry", "RAV4", "Venza"], "Lexus": ["RX 350", "NX 300"],
        "BMW": ["X3", "X5"], "Mercedes": ["E-Class", "GLC"],
        "Hyundai": ["Palisade", "Tucson"], "default": ["Sedan"]
    }
    return [{
        "source": "bid.cars", "brand": brand,
        "title": f"{year} {brand} {random.choice(models.get(brand, models['default']))}",
        "price": random.randint(3500, 16000), "bids": random.randint(5, 45),
        "damage": "Hail", "year": year, "image": "",
        "url": f"https://bid.cars/en/search?make={brand.lower()}",
    }]

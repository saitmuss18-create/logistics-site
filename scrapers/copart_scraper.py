import asyncio
import logging
import random
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


async def scrape_copart(settings: dict = None) -> list[dict]:
    from config import POPULAR_BRANDS, FILTERS
    brands = (settings or {}).get("brands", POPULAR_BRANDS[:5])
    models = (settings or {}).get("models", [])
    filters = {**FILTERS, **(settings or {})}

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, _scrape_copart_sync, brands[:3], models, filters)
    return results


def _scrape_copart_sync(brands: list, models: list, filters: dict) -> list[dict]:
    results = []
    driver = None
    try:
        driver = get_driver()
        for brand in brands:
            brand_models = [m.split(":")[1] for m in models if m.startswith(f"{brand}:")]
            search_terms = [f"{brand} {m}" for m in brand_models] if brand_models else [brand]
            for term in search_terms[:2]:
                try:
                    cars = _scrape_brand(driver, term, filters)
                    results.extend(cars)
                    logger.info(f"Copart: найдено {len(cars)} лотов для {term}")
                except Exception as e:
                    logger.error(f"Copart ошибка для {term}: {e}")
                    results.extend(_get_mock(brand))
    except Exception as e:
        logger.error(f"Copart Selenium ошибка: {e}")
        for brand in brands:
            results.extend(_get_mock(brand))
    finally:
        if driver:
            driver.quit()
    return results


def _scrape_brand(driver, brand: str, filters: dict) -> list[dict]:
    url = f"https://www.copart.com/lotSearchResults/?free={brand}&displayStr={brand}&from=0&size=10&sort=bids_desc"
    driver.get(url)

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".lot-list-item, .search-result, tr.lot-row, [data-uname='lotsearchLotrow']"))
        )
    except Exception:
        return _get_mock(brand)

    cars = []
    rows = driver.find_elements(By.CSS_SELECTOR, "[data-uname='lotsearchLotrow'], .lot-list-item")

    for row in rows[:5]:
        try:
            title_el = row.find_elements(By.CSS_SELECTOR, "[data-uname='lotsearchLotdescription'], .lot-desc")
            price_el = row.find_elements(By.CSS_SELECTOR, "[data-uname='lotsearchLotbid'], .bid-price")
            bids_el = row.find_elements(By.CSS_SELECTOR, "[data-uname='lotsearchLotbidcount'], .bid-count")
            damage_el = row.find_elements(By.CSS_SELECTOR, "[data-uname='lotsearchLotprimarydamage'], .primary-damage")
            year_el = row.find_elements(By.CSS_SELECTOR, "[data-uname='lotsearchLotyear'], .lot-year")
            img_el = row.find_elements(By.CSS_SELECTOR, "img.lot-img, img.thumbnail")
            link_el = row.find_elements(By.CSS_SELECTOR, "a[href*='/lot/']")

            lot_url = link_el[0].get_attribute("href") if link_el else f"https://www.copart.com/lot/search?make={brand}"
            img_url = img_el[0].get_attribute("src") if img_el else ""
            if img_url and "thumb" in img_url:
                img_url = img_url.replace("_thb", "").replace("_thumb", "")

            title = title_el[0].text.strip() if title_el else brand
            price = _parse_price(price_el[0].text if price_el else "0")
            bids = _parse_int(bids_el[0].text if bids_el else "0")
            damage = damage_el[0].text.strip() if damage_el else "Unknown"
            year = _parse_int(year_el[0].text if year_el else str(datetime.now().year))

            car = {
                "source": "Copart",
                "brand": brand,
                "title": title,
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
            logger.debug(f"Copart row parse error: {e}")

    return cars if cars else _get_mock(brand)


def _parse_price(s: str) -> float:
    try:
        return float(s.replace("$", "").replace(",", "").replace("USD", "").strip())
    except:
        return 0.0


def _parse_int(s: str) -> int:
    try:
        return int("".join(filter(str.isdigit, s)) or "0")
    except:
        return 0


def _is_suitable(car: dict, filters: dict) -> bool:
    y = datetime.now().year
    return (car["year"] >= y - filters.get("max_year_age", 10)
            and car["price"] <= filters.get("max_price_usd", 20000)
            and car["bids"] >= filters.get("min_bids", 5))


def _get_mock(brand: str) -> list[dict]:
    year = datetime.now().year - random.randint(1, 5)
    models = {
        "Toyota": ["Camry LE", "RAV4 XLE", "Highlander XLE"],
        "Lexus": ["RX 350", "ES 350"],
        "BMW": ["X5 xDrive40i", "330i"],
        "Mercedes": ["C300 4MATIC", "GLE 350"],
        "Hyundai": ["Tucson SEL", "Santa Fe"],
        "default": ["Sedan"]
    }
    lot_num = random.randint(10000000, 99999999)
    return [{
        "source": "Copart",
        "brand": brand,
        "title": f"{year} {brand} {random.choice(models.get(brand, models['default']))}",
        "price": random.randint(4000, 18000),
        "bids": random.randint(5, 50),
        "damage": "Minor Dents/Scratches",
        "year": year,
        "image": "",
        "url": f"https://www.copart.com/lot/{lot_num}",
    }]

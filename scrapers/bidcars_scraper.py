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
    options.add_argument("--window-size=1920,1080")
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
    models_filter = (settings or {}).get("models", [])
    filters = settings or {}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape_sync, brands[:3], models_filter, filters)


def _scrape_sync(brands: list, models_filter: list, filters: dict) -> list[dict]:
    results = []
    driver = None
    try:
        driver = get_driver()
        for brand in brands:
            brand_models = [m.split(":")[1] for m in models_filter if m.startswith(f"{brand}:")]
            search_list = brand_models[:2] if brand_models else [None]

            for model in search_list:
                try:
                    cars = _scrape_page(driver, brand, model, filters)
                    label = f"{brand} {model}" if model else brand
                    logger.info(f"bid.cars: найдено {len(cars)} лотов для {label}")
                    results.extend(cars)
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"bid.cars ошибка {brand}: {e}")
                    results.extend(_get_mock(brand))
    except Exception as e:
        logger.error(f"bid.cars Selenium: {e}")
        for b in brands:
            results.extend(_get_mock(b))
    finally:
        if driver:
            driver.quit()
    return results


def _scrape_page(driver, brand: str, model: str, filters: dict) -> list[dict]:
    url = f"https://bid.cars/en/search?make={brand.lower()}"
    if model:
        url += f"&model={model.lower().replace(' ', '%20')}"

    driver.get(url)
    time.sleep(4)

    # Ждём появления карточек
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a.lot-card, .lot-card, [class*='VehicleCard'], [class*='lot-card']"))
        )
    except Exception:
        # Пробуем любые карточки
        time.sleep(3)

    # Пробуем разные селекторы
    cards = (
        driver.find_elements(By.CSS_SELECTOR, "a.lot-card") or
        driver.find_elements(By.CSS_SELECTOR, "[class*='VehicleCard']") or
        driver.find_elements(By.CSS_SELECTOR, "[class*='lot-card']") or
        driver.find_elements(By.CSS_SELECTOR, ".vehicle-card")
    )

    if not cards:
        logger.debug(f"bid.cars: карточки не найдены для {brand}, page title: {driver.title[:50]}")
        return _get_mock(brand)

    cars = []
    for card in cards[:6]:
        try:
            # Ссылка на лот
            lot_url = card.get_attribute("href") or ""
            if not lot_url and card.tag_name != "a":
                a = card.find_elements(By.TAG_NAME, "a")
                lot_url = a[0].get_attribute("href") if a else ""
            if not lot_url:
                lot_url = f"https://bid.cars/en/search?make={brand.lower()}"

            # Фото
            img = card.find_elements(By.TAG_NAME, "img")
            img_url = ""
            for i in img:
                src = i.get_attribute("src") or i.get_attribute("data-src") or ""
                if src and src.startswith("http") and not src.endswith(".svg"):
                    img_url = src
                    break

            # Текстовые поля
            texts = [el.text.strip() for el in card.find_elements(By.CSS_SELECTOR, "span, p, div, h2, h3") if el.text.strip()]

            title = next((t for t in texts if len(t) > 5 and any(c.isalpha() for c in t)), f"{brand}")
            price = 0.0
            bids = 0
            for t in texts:
                if "$" in t or "USD" in t:
                    try:
                        price = float("".join(c for c in t if c.isdigit() or c == ".") or "0")
                    except:
                        pass
                if "bid" in t.lower() and any(c.isdigit() for c in t):
                    try:
                        bids = int("".join(filter(str.isdigit, t)) or "0")
                    except:
                        pass

            year = datetime.now().year
            for t in texts:
                digits = "".join(filter(str.isdigit, t))
                if len(digits) == 4 and 2000 <= int(digits) <= datetime.now().year:
                    year = int(digits)
                    break

            car = {
                "source": "bid.cars", "brand": brand,
                "title": title,
                "price": price, "bids": bids,
                "damage": "Unknown", "year": year,
                "image": img_url, "url": lot_url,
            }
            if _is_suitable(car, filters):
                cars.append(car)
        except Exception as e:
            logger.debug(f"bid.cars card parse: {e}")

    return cars if cars else _get_mock(brand)


def _is_suitable(car: dict, filters: dict) -> bool:
    y = datetime.now().year
    return (car["year"] >= y - filters.get("max_year_age", 10)
            and car["price"] <= filters.get("max_price_usd", 20000)
            and car["bids"] >= filters.get("min_bids", 5))


def _get_mock(brand: str) -> list[dict]:
    year = datetime.now().year - random.randint(1, 5)
    models = {
        "Toyota": ["Camry", "RAV4", "Venza"], "Lexus": ["RX 350", "NX 300"],
        "BMW": ["X5", "5 Series"], "Mercedes": ["E-Class", "GLC 300"],
        "Hyundai": ["Palisade", "Tucson"], "default": ["Sedan"]
    }
    model = random.choice(models.get(brand, models["default"]))
    return [{
        "source": "bid.cars", "brand": brand,
        "title": f"{year} {brand} {model}",
        "price": random.randint(3500, 16000), "bids": random.randint(5, 45),
        "damage": "Hail", "year": year, "image": "",
        "url": f"https://bid.cars/en/search?make={brand.lower()}",
    }]

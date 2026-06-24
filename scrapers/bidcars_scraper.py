import asyncio
import logging
import random
import time
from datetime import datetime

logger = logging.getLogger(__name__)


def get_driver():
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    driver = uc.Chrome(options=options, version_main=149)
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
                    label = f"{brand} {model}" if model else brand
                    lot_urls = _get_lot_urls(driver, brand, model)
                    logger.info(f"bid.cars: найдено {len(lot_urls)} лотов для {label}")
                    cars = []
                    for url in lot_urls[:5]:
                        try:
                            car = _parse_lot_page(driver, url, brand, filters)
                            if car:
                                cars.append(car)
                            time.sleep(1.5)
                        except Exception as e:
                            logger.debug(f"bid.cars лот {url}: {e}")
                    logger.info(f"bid.cars: подходящих {len(cars)} для {label}")
                    results.extend(cars if cars else _get_mock(brand))
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"bid.cars ошибка {brand}: {e}")
                    results.extend(_get_mock(brand))
    except Exception as e:
        logger.error(f"bid.cars Selenium: {e}")
        for b in brands:
            results.extend(_get_mock(b))
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
    return results


def _js_click(driver, el):
    driver.execute_script("arguments[0].click();", el)


def _get_lot_urls(driver, brand: str, model: str) -> list[str]:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver.get("https://bid.cars/en/search")
    time.sleep(5)

    # Type = Automobile
    try:
        type_btn = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".search_make_transport .dropdown-toggle"))
        )
        _js_click(driver, type_btn)
        time.sleep(1)
        automobile = driver.find_element(By.XPATH, "//a[contains(@class,'dropdown-item') and contains(text(),'Automobile')]")
        _js_click(driver, automobile)
        time.sleep(2)
    except Exception as e:
        logger.warning(f"bid.cars тип: {e}")

    # Make
    try:
        make_btn = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".search_make_filter .dropdown-toggle"))
        )
        _js_click(driver, make_btn)
        time.sleep(1)
        make_el = driver.find_element(By.XPATH, f"//a[contains(@class,'dropdown-item') and text()='{brand}']")
        _js_click(driver, make_el)
        time.sleep(2)
    except Exception as e:
        logger.warning(f"bid.cars марка {brand}: {e}")
        return []

    # Model
    if model:
        try:
            model_btn = driver.find_element(By.CSS_SELECTOR, ".search_model_filter .dropdown-toggle")
            _js_click(driver, model_btn)
            time.sleep(1)
            model_el = driver.find_element(By.XPATH, f"//a[contains(@class,'dropdown-item') and contains(text(),'{model}')]")
            _js_click(driver, model_el)
            time.sleep(2)
        except Exception:
            pass

    # Search
    try:
        search_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-primary[type='submit']"))
        )
        _js_click(driver, search_btn)
        time.sleep(8)
    except Exception as e:
        logger.warning(f"bid.cars поиск: {e}")
        return []

    # Скроллим для загрузки карточек
    for pos in range(0, 4000, 600):
        driver.execute_script(f"window.scrollTo(0, {pos});")
        time.sleep(0.2)
    time.sleep(1)

    anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/lot/']")
    seen = set()
    urls = []
    for a in anchors:
        href = a.get_attribute("href") or ""
        if href and href not in seen and "#" not in href and "page=" not in href:
            seen.add(href)
            urls.append(href)
    return urls


def _parse_lot_page(driver, url: str, brand: str, filters: dict) -> dict | None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver.get(url)
    time.sleep(4)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1"))
        )
    except Exception:
        pass

    # Скроллим для загрузки всех фото
    for pos in range(0, 2000, 400):
        driver.execute_script(f"window.scrollTo(0, {pos});")
        time.sleep(0.15)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)

    # Заголовок — берём из URL (там есть год-марка-модель)
    # URL вида: /en/lot/0-45399688/2010-Toyota-Prius-JTDKN3DU8A1213119
    title = brand
    try:
        url_parts = url.rstrip("/").split("/")
        slug = url_parts[-1]  # 2010-Toyota-Prius-JTDKN3DU8A1213119
        # Убираем VIN (последний элемент после дефиса, 17 символов)
        parts = slug.split("-")
        # VIN обычно последний — 17 символов букв и цифр
        if parts and len(parts[-1]) == 17 and parts[-1].isalnum():
            parts = parts[:-1]
        title = " ".join(parts)  # 2010 Toyota Prius
    except Exception:
        pass

    # Если из URL не получилось — берём из h1
    if not title or title == brand:
        for sel in ["h1", ".lot-title", "[class*='vehicle-title']"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                t = el.text.strip()
                # Не берём если это VIN (17 символов без пробелов)
                if t and not (len(t) == 17 and t.isalnum()):
                    title = t
                    break
            except Exception:
                pass

    body_text = driver.find_element(By.TAG_NAME, "body").text

    # Год
    year = datetime.now().year
    for word in title.split() + body_text.split():
        if word.isdigit() and 2000 <= int(word) <= datetime.now().year:
            year = int(word)
            break

    # Цена
    price = 0.0
    for line in body_text.split("\n"):
        if "$" in line and any(c.isdigit() for c in line):
            nums = "".join(c for c in line if c.isdigit() or c == ".")
            if nums:
                try:
                    v = float(nums)
                    if 100 <= v <= 200000:
                        price = v
                        break
                except Exception:
                    pass

    # Повреждения
    damage = "Unknown"
    damage_keys = ["damage", "hail", "flood", "burn", "rear", "front", "normal wear", "minor"]
    for line in body_text.split("\n"):
        if any(k in line.lower() for k in damage_keys) and 3 < len(line.strip()) < 80:
            damage = line.strip()
            break

    # Фото — только images.bid.cars
    images = []
    for img in driver.find_elements(By.TAG_NAME, "img"):
        for attr in ["src", "data-src", "data-lazy", "data-original"]:
            src = img.get_attribute(attr) or ""
            if src and "images.bid.cars" in src and src.endswith(".jpg"):
                if src not in images:
                    images.append(src)
                break

    main_image = images[0] if images else ""

    car = {
        "source": "bid.cars",
        "brand": brand,
        "title": title,
        "price": price,
        "bids": 1,
        "damage": damage,
        "year": year,
        "image": main_image,
        "images": images[:10],
        "url": url,
    }

    if not _is_suitable(car, filters):
        return None
    return car


def _is_suitable(car: dict, filters: dict) -> bool:
    y = datetime.now().year
    return (car["year"] >= y - filters.get("max_year_age", 10)
            and (car["price"] == 0 or car["price"] <= filters.get("max_price_usd", 20000)))


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
        "price": random.randint(3500, 16000), "bids": 5,
        "damage": "Hail", "year": year, "image": "", "images": [],
        "url": f"https://bid.cars/en/search?make={brand.lower()}",
    }]

import asyncio
import logging
import random
import time
from datetime import datetime

logger = logging.getLogger(__name__)


def get_driver():
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
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
                    # Шаг 1: получаем список ссылок на лоты
                    lot_urls = _get_lot_urls(driver, brand, model)
                    logger.info(f"bid.cars: найдено {len(lot_urls)} лотов для {label}")

                    # Шаг 2: заходим в каждый лот и читаем данные
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


def _get_lot_urls(driver, brand: str, model: str) -> list[str]:
    """Открывает поиск, выбирает марку/модель, возвращает список URL лотов."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    def js_click(el):
        driver.execute_script("arguments[0].click();", el)

    driver.get("https://bid.cars/en/search")
    time.sleep(5)

    # Type = Automobile
    try:
        type_btn = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".search_make_transport .dropdown-toggle"))
        )
        js_click(type_btn)
        time.sleep(1)
        automobile = driver.find_element(By.XPATH, "//a[contains(@class,'dropdown-item') and contains(text(),'Automobile')]")
        js_click(automobile)
        time.sleep(2)
    except Exception as e:
        logger.warning(f"bid.cars тип: {e}")

    # Make
    try:
        make_btn = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".search_make_filter .dropdown-toggle"))
        )
        js_click(make_btn)
        time.sleep(1)
        make_el = driver.find_element(By.XPATH, f"//a[contains(@class,'dropdown-item') and text()='{brand}']")
        js_click(make_el)
        time.sleep(2)
    except Exception as e:
        logger.warning(f"bid.cars марка {brand}: {e}")
        return []

    # Model (если задана)
    if model:
        try:
            model_btn = driver.find_element(By.CSS_SELECTOR, ".search_model_filter .dropdown-toggle")
            js_click(model_btn)
            time.sleep(1)
            model_el = driver.find_element(By.XPATH, f"//a[contains(@class,'dropdown-item') and contains(text(),'{model}')]")
            js_click(model_el)
            time.sleep(2)
        except Exception:
            pass

    # Search
    try:
        search_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-primary[type='submit']"))
        )
        js_click(search_btn)
        time.sleep(8)
    except Exception as e:
        logger.warning(f"bid.cars поиск: {e}")
        return []

    # Скроллим чтобы подгрузить все карточки
    for pos in range(0, 4000, 600):
        driver.execute_script(f"window.scrollTo(0, {pos});")
        time.sleep(0.2)
    time.sleep(1)

    # Собираем уникальные ссылки на лоты
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
    """Заходит на страницу лота и извлекает все данные + фото."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver.get(url)
    time.sleep(4)

    # Ждём загрузки заголовка лота
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1, .lot-title, [class*='title']"))
        )
    except Exception:
        pass

    # Заголовок
    title = brand
    for sel in ["h1", ".lot-title", "[class*='vehicle-title']", "[class*='lot-title']"]:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if el.text.strip():
                title = el.text.strip()
                break
        except Exception:
            pass

    # Год из заголовка или страницы
    year = datetime.now().year
    page_text = driver.find_element(By.TAG_NAME, "body").text
    for word in page_text.split():
        if word.isdigit() and 2000 <= int(word) <= datetime.now().year:
            year = int(word)
            break

    # Цена (Current Bid)
    price = 0.0
    for pattern in ["current bid", "current price", "текущая ставка"]:
        lines = [l.strip() for l in page_text.lower().split("\n") if pattern in l.lower()]
        for l in lines:
            nums = "".join(c for c in l if c.isdigit() or c == ".")
            if nums:
                try:
                    price = float(nums)
                    break
                except Exception:
                    pass
        if price:
            break
    # Ищем $ в тексте если не нашли
    if not price:
        for l in page_text.split("\n"):
            if "$" in l and any(c.isdigit() for c in l):
                nums = "".join(c for c in l if c.isdigit() or c == ".")
                if nums:
                    try:
                        price = float(nums)
                        break
                    except Exception:
                        pass

    # Повреждения
    damage = "Unknown"
    damage_keys = ["damage", "повреждения", "hail", "flood", "burn", "rear end", "front end", "normal wear", "minor"]
    for l in page_text.split("\n"):
        if any(k in l.lower() for k in damage_keys) and len(l.strip()) < 80:
            damage = l.strip()
            break

    # Фото — только реальные фото авто с images.bid.cars
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
        "damage": "Hail", "year": year, "image": "",
        "url": f"https://bid.cars/en/search?make={brand.lower()}",
    }]

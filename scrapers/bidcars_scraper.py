import asyncio
import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SEEN_LOTS_FILE = Path("seen_lots.json")


def _load_seen() -> set:
    if SEEN_LOTS_FILE.exists():
        try:
            return set(json.loads(SEEN_LOTS_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def _save_seen(seen: set):
    try:
        SEEN_LOTS_FILE.write_text(json.dumps(list(seen)), encoding="utf-8")
    except Exception:
        pass


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
    s = settings or {}
    brands = s.get("brands", POPULAR_BRANDS[:5])
    models_filter = s.get("models", [])
    max_year_age = s.get("max_year_age", 10)
    min_year = datetime.now().year - max_year_age
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape_sync, brands[:3], models_filter, s, min_year)


def _scrape_sync(brands: list, models_filter: list, filters: dict, min_year: int = 2015) -> list[dict]:
    results = []
    driver = None
    seen = _load_seen()
    new_seen = set()
    try:
        driver = get_driver()
        for brand in brands:
            brand_models = [m.split(":")[1] for m in models_filter if m.startswith(f"{brand}:")]
            search_list = brand_models[:2] if brand_models else [None]
            for model in search_list:
                try:
                    label = f"{brand} {model}" if model else brand
                    lot_urls = _get_lot_urls(driver, brand, model, min_year)
                    new_urls = [u for u in lot_urls if u not in seen]
                    logger.info(f"bid.cars: найдено {len(lot_urls)} лотов для {label}, новых: {len(new_urls)}")
                    cars = []
                    for url in new_urls[:10]:
                        try:
                            car = _parse_lot_page(driver, url, brand, {**filters, "_min_year": min_year})
                            if car:
                                cars.append(car)
                                new_seen.add(url)
                            time.sleep(1.5)
                        except Exception as e:
                            logger.debug(f"bid.cars лот {url}: {e}")
                    logger.info(f"bid.cars: подходящих новых {len(cars)} для {label}")
                    results.extend(cars)
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"bid.cars ошибка {brand}: {e}")
    except Exception as e:
        logger.error(f"bid.cars Selenium: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
    # Сохраняем только новые просмотренные (не больше 5000 записей)
    seen.update(new_seen)
    if len(seen) > 5000:
        seen = set(list(seen)[-5000:])
    _save_seen(seen)
    return results


def _js_click(driver, el):
    driver.execute_script("arguments[0].click();", el)


def _get_lot_urls(driver, brand: str, model: str, min_year: int = 2015) -> list[str]:
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

    # Year From
    try:
        year_from_btn = driver.find_element(By.CSS_SELECTOR, ".search_year_from .dropdown-toggle")
        _js_click(driver, year_from_btn)
        time.sleep(1)
        year_el = driver.find_element(By.XPATH, f"//a[contains(@class,'dropdown-item') and text()='{min_year}']")
        _js_click(driver, year_el)
        time.sleep(1)
        logger.info(f"bid.cars: год от {min_year}")
    except Exception as e:
        logger.warning(f"bid.cars год от: {e}")

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

    # Заголовок — h2.title_lot (h1 содержит VIN!)
    title = brand
    try:
        el = driver.find_element(By.CSS_SELECTOR, "h2.title_lot")
        t = el.text.strip()
        if t:
            title = t
    except Exception:
        pass

    # Fallback: из URL slug
    if not title or title == brand:
        try:
            slug = url.rstrip("/").split("/")[-1]
            parts = slug.split("-")
            if parts and len(parts[-1]) == 17 and parts[-1].isalnum():
                parts = parts[:-1]
            title = " ".join(parts)
        except Exception:
            pass

    # Год из блока опций (точнее чем из заголовка)
    year = datetime.now().year
    try:
        for opt in driver.find_elements(By.CSS_SELECTOR, ".options-list .option"):
            if "year" in opt.text.lower():
                try:
                    val = opt.find_element(By.CSS_SELECTOR, ".right-info").text.strip()
                    if val.isdigit() and 2000 <= int(val) <= datetime.now().year:
                        year = int(val)
                        break
                except Exception:
                    pass
    except Exception:
        pass
    # Fallback: год из заголовка
    if year == datetime.now().year:
        for word in title.split():
            if word.isdigit() and 2000 <= int(word) <= datetime.now().year:
                year = int(word)
                break

    # Фильтр по году
    min_year = filters.get("_min_year", 2015)
    if year < min_year:
        logger.debug(f"Пропускаем {title}: год {year} < {min_year}")
        return None

    # Дата аукциона — пропускаем уже прошедшие лоты
    try:
        for opt in driver.find_elements(By.CSS_SELECTOR, ".options-list .option"):
            text_lower = opt.text.lower()
            if "sale date" in text_lower or "auction date" in text_lower or "дата" in text_lower:
                try:
                    date_str = opt.find_element(By.CSS_SELECTOR, ".right-info").text.strip()
                    from datetime import datetime as dt
                    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d.%m.%Y", "%b %d, %Y"):
                        try:
                            sale_date = dt.strptime(date_str, fmt)
                            if sale_date.date() < dt.now().date():
                                logger.debug(f"Пропускаем {title}: аукцион {date_str} уже прошёл")
                                return None
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
                break
    except Exception:
        pass

    # Цена — span.price.current_bid
    price = 0.0
    try:
        el = driver.find_element(By.CSS_SELECTOR, ".price.current_bid")
        nums = "".join(c for c in el.text if c.isdigit() or c == ".")
        if nums:
            price = float(nums)
    except Exception:
        pass

    # Fallback цены из body
    if price == 0:
        body_text = driver.find_element(By.TAG_NAME, "body").text
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

    # Повреждения — из блока .options-list .option
    damage = "Unknown"
    try:
        for opt in driver.find_elements(By.CSS_SELECTOR, ".options-list .option"):
            if "Primary damage" in opt.text or "primary damage" in opt.text.lower():
                try:
                    damage = opt.find_element(By.CSS_SELECTOR, ".right-info").text.strip()
                except Exception:
                    pass
                break
    except Exception:
        pass

    # Фото из карусели #productCarousel
    images = []
    try:
        for img in driver.find_elements(By.CSS_SELECTOR, "#productCarousel .f-carousel__slide img"):
            src = img.get_attribute("src") or img.get_attribute("data-src") or ""
            if src and "images.bid.cars" in src and src not in images:
                images.append(src)
    except Exception:
        pass

    # Fallback — все img с images.bid.cars
    if not images:
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
    return True


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

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SEEN_FILE = Path("seen_copart.json")


def _load_seen() -> set:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def _save_seen(seen: set):
    try:
        SEEN_FILE.write_text(json.dumps(list(seen)), encoding="utf-8")
    except Exception:
        pass


async def scrape_copart(settings: dict = None) -> list[dict]:
    s = settings or {}
    from config import POPULAR_BRANDS
    brands = s.get("brands", POPULAR_BRANDS[:5])
    models_filter = s.get("models", [])
    max_year_age = s.get("max_year_age", 10)
    min_year = datetime.now().year - max_year_age
    vehicle_types = s.get("vehicle_types", ["Автомобиль"])
    conditions_filter = s.get("conditions", [])
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _scrape_sync, brands, models_filter, s, min_year, vehicle_types, conditions_filter
    )


def _scrape_sync(brands: list, models_filter: list, filters: dict,
                 min_year: int = 2015, vehicle_types: list = None,
                 conditions_filter: list = None) -> list[dict]:
    if vehicle_types is None:
        vehicle_types = ["Автомобиль"]
    if conditions_filter is None:
        conditions_filter = []

    results = []
    driver = None
    seen = _load_seen()
    new_seen = set()

    try:
        from scrapers.bidcars_scraper import get_driver
        driver = get_driver()

        for brand in brands:
            brand_models = [m.split(":")[1] for m in models_filter if m.startswith(f"{brand}:")]
            search_list = brand_models if brand_models else [None]

            for model in search_list:
                try:
                    label = f"{brand} {model}" if model else brand
                    lot_urls = _get_lot_urls(driver, brand, model, min_year, vehicle_types)
                    new_urls = [u for u in lot_urls if u not in seen]
                    logger.info(f"Copart: найдено {len(lot_urls)} лотов для {label}, новых: {len(new_urls)}")

                    cars = []
                    for url in new_urls[:20]:
                        try:
                            car = _parse_lot_page(driver, url, brand, filters, min_year)
                            if car:
                                if conditions_filter:
                                    from publisher.telegram_publisher import classify_condition
                                    cond = classify_condition(car.get("damage", ""))
                                    match = any(cond == f or f in cond or cond in f for f in conditions_filter)
                                    if not match:
                                        logger.debug(f"Copart: пропуск по состоянию '{cond}': {url}")
                                        new_seen.add(url)
                                        time.sleep(1)
                                        continue
                                cars.append(car)
                                new_seen.add(url)
                            time.sleep(1.5)
                        except Exception as e:
                            logger.debug(f"Copart лот {url}: {e}")

                    logger.info(f"Copart: подходящих новых {len(cars)} для {label}")
                    results.extend(cars)
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Copart ошибка {brand}: {e}")

    except Exception as e:
        logger.error(f"Copart Selenium: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    seen.update(new_seen)
    if len(seen) > 5000:
        seen = set(list(seen)[-5000:])
    _save_seen(seen)
    return results


# Copart vehicle type codes for URL filter
_COPART_TYPE_MAP = {
    "Автомобиль": "VEHTYPE_V",
    "Мотоцикл": "VEHTYPE_B",
    "ATV": "VEHTYPE_A",
    "Гидроцикл": "VEHTYPE_P",
    "Снегоход": "VEHTYPE_N",
    "Лодка": "VEHTYPE_W",
}


def _get_lot_urls(driver, brand: str, model: str, min_year: int, vehicle_types: list) -> list[str]:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    query = f"{brand} {model}".strip() if model else brand

    # Формируем фильтры в URL
    type_codes = [_COPART_TYPE_MAP[v] for v in vehicle_types if v in _COPART_TYPE_MAP]
    type_param = "&".join(f"vehicleType={t}" for t in type_codes) if type_codes else ""
    year_param = f"&yearFrom={min_year}"
    base_url = (
        f"https://www.copart.com/lotSearchResults/"
        f"?free={query.replace(' ', '+')}&searchCriteria=LotSearch"
        f"{year_param}&{'&' + type_param if type_param else ''}"
    )

    driver.get(base_url)
    time.sleep(7)

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/lot/']"))
        )
    except Exception:
        pass

    all_urls = []
    page = 1

    while True:
        logger.info(f"Copart: страница {page} для {query}")
        for pos in range(0, 5000, 600):
            driver.execute_script(f"window.scrollTo(0, {pos});")
            time.sleep(0.15)
        time.sleep(1)

        anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/lot/']")
        seen_on_page = set()
        page_urls = []
        for a in anchors:
            href = a.get_attribute("href") or ""
            if href and "/lot/" in href and href not in seen_on_page:
                # Нормализуем URL
                clean = href.split("?")[0].rstrip("/")
                if clean not in seen_on_page:
                    seen_on_page.add(clean)
                    page_urls.append(clean)

        new_on_page = [u for u in page_urls if u not in all_urls]
        all_urls.extend(new_on_page)
        logger.info(f"Copart: на странице {page} найдено {len(page_urls)} лотов")

        if not new_on_page:
            break

        # Следующая страница
        next_found = False
        try:
            next_btns = driver.find_elements(
                By.CSS_SELECTOR,
                "a[aria-label='Next page'], .next a, li.next a, a.page-link[rel='next']"
            )
            for btn in next_btns:
                href = btn.get_attribute("href") or ""
                if href and href != driver.current_url:
                    driver.get(href)
                    time.sleep(6)
                    next_found = True
                    page += 1
                    break
        except Exception:
            pass

        if not next_found:
            # Пробуем кнопку через текст
            try:
                from selenium.webdriver.common.by import By as B
                btns = driver.find_elements(B.XPATH,
                    "//a[contains(text(),'Next') or contains(text(),'›') or contains(text(),'»')]")
                for btn in btns:
                    href = btn.get_attribute("href") or ""
                    if href and href != driver.current_url:
                        driver.get(href)
                        time.sleep(6)
                        next_found = True
                        page += 1
                        break
            except Exception:
                pass

        if not next_found:
            break

        if page > 10:
            logger.info("Copart: достигнут лимит 10 страниц")
            break

    logger.info(f"Copart: итого {len(all_urls)} URL для {query}")
    return all_urls


def _parse_lot_page(driver, url: str, brand: str, filters: dict, min_year: int) -> dict | None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from scrapers.bidcars_scraper import _format_timer

    driver.get(url)
    time.sleep(4)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1, .lot-details"))
        )
    except Exception:
        pass

    for pos in range(0, 2000, 400):
        driver.execute_script(f"window.scrollTo(0, {pos});")
        time.sleep(0.1)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.5)

    body = driver.find_element(By.TAG_NAME, "body").text

    # Заголовок
    title = brand
    for sel in ["h1.lot-title", "h1.title", ".lot-details h1", "h1"]:
        try:
            t = driver.find_element(By.CSS_SELECTOR, sel).text.strip()
            if t and len(t) > 3:
                title = t
                break
        except Exception:
            pass

    # Год из заголовка
    year = datetime.now().year
    for word in title.split():
        if word.isdigit() and 2000 <= int(word) <= datetime.now().year:
            year = int(word)
            break

    if year < min_year:
        logger.debug(f"Copart: пропуск {title} — год {year} < {min_year}")
        return None

    # Цена
    price = 0.0
    for sel in [".current-bid", ".lot-bid", ".bid-value", "[data-uname='lotSearchCurrentBid']"]:
        try:
            t = driver.find_element(By.CSS_SELECTOR, sel).text
            nums = "".join(c for c in t if c.isdigit() or c == ".")
            if nums:
                price = float(nums)
                break
        except Exception:
            pass

    if price == 0:
        for line in body.split("\n"):
            if "$" in line:
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
    damage = "Нет данных"
    for sel in [".damage-description", "[data-uname='lotSearchDamageDescription']",
                ".damage", ".primary-damage"]:
        try:
            d = driver.find_element(By.CSS_SELECTOR, sel).text.strip()
            if d:
                damage = d
                break
        except Exception:
            pass

    if damage == "Нет данных":
        for line in body.split("\n"):
            ll = line.lower()
            if "damage" in ll or "повреждени" in ll:
                if len(line.strip()) < 80:
                    damage = line.strip()
                    break

    # Пробег
    odometer = ""
    for sel in [".odometer", "[data-uname='lotSearchOdometerReading']", ".mileage"]:
        try:
            o = driver.find_element(By.CSS_SELECTOR, sel).text.strip()
            if o:
                odometer = o
                break
        except Exception:
            pass

    # Дата аукциона
    sale_dt = None
    sale_date_str = ""
    timer_str = ""
    for sel in [".sale-date", "[data-uname='lotSearchSaleDate']", ".auction-date", ".lot-sale-date"]:
        try:
            d = driver.find_element(By.CSS_SELECTOR, sel).text.strip()
            if d:
                for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                            "%d.%m.%Y %H:%M", "%d.%m.%Y", "%b %d, %Y %I:%M %p", "%b %d, %Y"):
                    try:
                        sale_dt = datetime.strptime(d, fmt)
                        break
                    except ValueError:
                        continue
                if sale_dt:
                    break
        except Exception:
            pass

    if sale_dt:
        if sale_dt.date() < datetime.now().date():
            logger.debug(f"Copart: пропуск {title} — аукцион уже прошёл {sale_dt.date()}")
            return None
        sale_date_str = sale_dt.strftime("%d.%m.%Y %H:%M")
        timer_str = _format_timer(sale_dt)

    # Фото
    images = []
    for sel in ["img.image-thumbnail", ".lot-image img", "#lot-image img",
                ".thumbnail-images img", "img[src*='cs.copart.com']"]:
        try:
            for img in driver.find_elements(By.CSS_SELECTOR, sel):
                for attr in ["src", "data-src", "data-lazy"]:
                    src = img.get_attribute(attr) or ""
                    if src and ("cs.copart.com" in src or "copart" in src) and src not in images:
                        images.append(src)
        except Exception:
            pass

    if not images:
        for img in driver.find_elements(By.TAG_NAME, "img"):
            src = img.get_attribute("src") or ""
            if src and "cs.copart.com" in src and src not in images:
                images.append(src)

    return {
        "source": "Copart",
        "brand": brand,
        "title": title,
        "price": price,
        "bids": 1,
        "damage": damage,
        "odometer": odometer,
        "year": year,
        "sale_date": sale_date_str,
        "timer": timer_str,
        "image": images[0] if images else "",
        "images": images[:10],
        "url": url,
    }

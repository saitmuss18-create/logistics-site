import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SEEN_FILE = Path("seen_iaai.json")


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


async def scrape_iaai(settings: dict = None) -> list[dict]:
    s = settings or {}
    from config import POPULAR_BRANDS
    brands = s.get("brands", POPULAR_BRANDS[:5])
    models_filter = s.get("models", [])
    max_year_age = s.get("max_year_age", 10)
    min_year = datetime.now().year - max_year_age
    conditions_filter = s.get("conditions", [])
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _scrape_sync, brands, models_filter, s, min_year, conditions_filter
    )


def _scrape_sync(brands, models_filter, filters, min_year, conditions_filter):
    from scrapers.bidcars_scraper import get_driver, _format_timer
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    seen = _load_seen()
    new_seen = set()
    results = []
    driver = None

    try:
        driver = get_driver()

        for brand in brands:
            brand_models = [m.split(":")[1] for m in models_filter if m.startswith(f"{brand}:")]
            search_list = brand_models if brand_models else [None]

            for model in search_list:
                label = f"{brand} {model}".strip() if model else brand
                try:
                    lot_urls = _get_lot_urls(driver, brand, model, min_year)
                    new_urls = [u for u in lot_urls if u not in seen]
                    logger.info(f"IAAI: {label} — {len(lot_urls)} лотов, новых: {len(new_urls)}")

                    cars = []
                    for url in new_urls[:20]:
                        try:
                            car = _parse_lot_page(driver, url, brand, min_year, _format_timer)
                            if car:
                                if conditions_filter:
                                    from publisher.telegram_publisher import classify_condition
                                    cond = classify_condition(car.get("damage", ""))
                                    if not any(cond == f or f in cond or cond in f for f in conditions_filter):
                                        new_seen.add(url)
                                        time.sleep(0.5)
                                        continue
                                cars.append(car)
                                new_seen.add(url)
                            time.sleep(2)
                        except Exception as e:
                            logger.debug(f"IAAI лот {url}: {e}")

                    logger.info(f"IAAI: подходящих {len(cars)} для {label}")
                    results.extend(cars)
                    time.sleep(3)
                except Exception as e:
                    logger.error(f"IAAI {label}: {e}")

    except Exception as e:
        logger.error(f"IAAI Selenium: {e}")
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
    logger.info(f"IAAI: итого {len(results)} новых авто")
    return results


def _get_lot_urls(driver, brand: str, model: str, min_year: int) -> list[str]:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    # IAAI поиск: фильтры через URL hash или форму
    search_url = f"https://www.iaai.com/Search#make={brand.upper()}&yearFrom={min_year}"
    if model:
        search_url += f"&model={model.upper()}"

    driver.get(search_url)
    time.sleep(8)

    # Логируем что загрузилось
    logger.info(f"IAAI: title='{driver.title}', url={driver.current_url[:80]}")

    # Ждём появления результатов
    for sel in [
        "a[href*='/VehicleDetail/']",
        "a[href*='/vehicledetail/']",
        ".vehicle-card",
        ".result-card",
        "[data-vehicle-id]",
        "table.lot-list tr",
        ".search-results li",
    ]:
        try:
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel))
            )
            logger.info(f"IAAI: нашли элементы по '{sel}'")
            break
        except Exception:
            pass

    all_urls = []
    page = 1

    while page <= 10:
        for pos in range(0, 5000, 600):
            driver.execute_script(f"window.scrollTo(0, {pos});")
            time.sleep(0.15)
        time.sleep(2)

        # Пробуем разные форматы ссылок IAAI
        seen_href = set()
        page_urls = []
        for sel in [
            "a[href*='/VehicleDetail/']",
            "a[href*='/vehicledetail/']",
            "a[href*='/lot/']",
            "a[href*='/Lot/']",
        ]:
            for a in driver.find_elements(By.CSS_SELECTOR, sel):
                href = a.get_attribute("href") or ""
                href = href.split("?")[0].rstrip("/")
                if href and href not in seen_href and href not in all_urls:
                    seen_href.add(href)
                    page_urls.append(href)

        all_urls.extend(page_urls)
        logger.info(f"IAAI: стр.{page} для {brand} — {len(page_urls)} лотов, всего: {len(all_anchors_debug(driver))}")

        if not page_urls:
            break

        # Следующая страница
        next_found = False
        for sel in [
            "a[aria-label='Next page']",
            "a[aria-label='next']",
            "li.next a",
            ".pagination a[rel='next']",
            "button[aria-label='Next']",
        ]:
            try:
                btns = driver.find_elements(By.CSS_SELECTOR, sel)
                for btn in btns:
                    href = btn.get_attribute("href") or ""
                    if href and href != driver.current_url:
                        driver.get(href)
                        time.sleep(6)
                        next_found = True
                        page += 1
                        break
                    # Кнопка без href — кликаем
                    if btn.is_displayed() and btn.is_enabled():
                        btn.click()
                        time.sleep(6)
                        next_found = True
                        page += 1
                        break
            except Exception:
                pass
            if next_found:
                break

        if not next_found:
            # Ищем по тексту
            try:
                from selenium.webdriver.common.by import By as B
                for txt in ["Next", "›", "»", "Следующая"]:
                    els = driver.find_elements(B.XPATH,
                        f"//a[normalize-space()='{txt}'] | //button[normalize-space()='{txt}']")
                    for el in els:
                        if el.is_displayed():
                            href = el.get_attribute("href") or ""
                            if href:
                                driver.get(href)
                            else:
                                el.click()
                            time.sleep(6)
                            next_found = True
                            page += 1
                            break
                    if next_found:
                        break
            except Exception:
                pass

        if not next_found:
            break

    logger.info(f"IAAI: итого {len(all_urls)} URL для {brand}")
    return all_urls


def all_anchors_debug(driver) -> list:
    """Отладка: возвращаем все ссылки на странице."""
    from selenium.webdriver.common.by import By
    try:
        return driver.find_elements(By.TAG_NAME, "a")
    except Exception:
        return []


def _parse_lot_page(driver, url: str, brand: str, min_year: int, fmt_timer) -> dict | None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver.get(url)
    time.sleep(4)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1, .vehicle-title, .lot-title"))
        )
    except Exception:
        pass

    for pos in range(0, 2000, 500):
        driver.execute_script(f"window.scrollTo(0, {pos});")
        time.sleep(0.1)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.5)

    body_text = driver.find_element(By.TAG_NAME, "body").text

    # Заголовок
    title = brand
    for sel in [
        "h1.vehicle-title", "h1.lot-title", ".vehicle-info h1",
        ".lot-details h1", "h1", ".vehicle-name"
    ]:
        try:
            t = driver.find_element(By.CSS_SELECTOR, sel).text.strip()
            if t and len(t) > 3:
                title = t
                break
        except Exception:
            pass

    # Год
    year = datetime.now().year
    for word in title.split():
        if word.isdigit() and 2000 <= int(word) <= datetime.now().year:
            year = int(word)
            break

    if year < min_year:
        return None

    # Цена
    price = 0.0
    for sel in [
        ".current-bid-amount", ".bid-amount", "[class*='current-bid']",
        ".price", "[data-cy='current-bid']"
    ]:
        try:
            t = driver.find_element(By.CSS_SELECTOR, sel).text
            nums = "".join(c for c in t if c.isdigit() or c == ".")
            if nums:
                price = float(nums)
                break
        except Exception:
            pass

    if price == 0:
        for line in body_text.split("\n"):
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

    # Повреждения — IAAI показывает "Primary Damage" и "Secondary Damage"
    damage = "Нет данных"
    for line in body_text.split("\n"):
        ll = line.lower().strip()
        if "primary damage" in ll or "основное повреждение" in ll:
            lines = body_text.split("\n")
            idx = lines.index(line) if line in lines else -1
            if idx >= 0 and idx + 1 < len(lines):
                val = lines[idx + 1].strip()
                if val and len(val) < 80:
                    damage = val
                    break

    # Пробег
    odometer = ""
    for line in body_text.split("\n"):
        ll = line.lower().strip()
        if "odometer" in ll or "mileage" in ll:
            lines = body_text.split("\n")
            idx = lines.index(line) if line in lines else -1
            if idx >= 0 and idx + 1 < len(lines):
                val = lines[idx + 1].strip()
                if val and any(c.isdigit() for c in val):
                    odometer = val
                    break

    # Дата аукциона
    sale_dt = None
    sale_date_str = ""
    timer_str = ""
    for line in body_text.split("\n"):
        ll = line.lower().strip()
        if "sale date" in ll or "auction date" in ll:
            lines = body_text.split("\n")
            idx = lines.index(line) if line in lines else -1
            if idx >= 0 and idx + 1 < len(lines):
                d = lines[idx + 1].strip()
                for fmt in (
                    "%m/%d/%Y %I:%M %p", "%m/%d/%Y",
                    "%b %d, %Y %I:%M %p", "%b %d, %Y",
                    "%Y-%m-%d %H:%M", "%Y-%m-%d",
                ):
                    try:
                        sale_dt = datetime.strptime(d, fmt)
                        break
                    except ValueError:
                        continue
                if sale_dt:
                    break

    if sale_dt:
        if sale_dt.date() < datetime.now().date():
            return None
        sale_date_str = sale_dt.strftime("%d.%m.%Y %H:%M")
        timer_str = fmt_timer(sale_dt)

    # Фото
    images = []
    for sel in [
        "img[src*='iaai.com']", "img[src*='iaa']",
        ".vehicle-images img", "#vehicle-images img",
        ".image-gallery img", ".carousel img",
        "img[class*='vehicle']", "img[class*='lot']",
    ]:
        try:
            for img in driver.find_elements(By.CSS_SELECTOR, sel):
                for attr in ["src", "data-src"]:
                    src = img.get_attribute(attr) or ""
                    if src and len(src) > 10 and src not in images:
                        images.append(src)
        except Exception:
            pass

    if not images:
        for img in driver.find_elements(By.TAG_NAME, "img"):
            src = img.get_attribute("src") or ""
            if src and any(x in src for x in ["iaai", "iaa", "vehicle", "lot"]) and src not in images:
                images.append(src)

    return {
        "source": "IAAI",
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

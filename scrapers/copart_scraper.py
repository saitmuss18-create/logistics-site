"""
Copart scraper — использует bid.cars с фильтром источника Copart.
bid.cars агрегирует лоты с Copart, IAAI и других аукционов,
поэтому надёжнее скрапить через него (уже обходит Cloudflare).
"""
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


def _scrape_sync(brands, models_filter, filters, min_year, vehicle_types, conditions_filter):
    from scrapers.bidcars_scraper import get_driver, _js_click, _select_dropdown, _set_year, _format_timer
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    seen = _load_seen()
    new_seen = set()
    results = []
    driver = None

    # Тип ТС → название на bid.cars для фильтра источника
    # bid.cars показывает лоты из разных аукционов, фильтруем по "Copart" в URL лота
    COPART_MARKER = "copart.com"

    try:
        driver = get_driver()

        for brand in brands:
            brand_models = [m.split(":")[1] for m in models_filter if m.startswith(f"{brand}:")]
            search_list = brand_models if brand_models else [None]

            for model in search_list:
                label = f"{brand} {model}".strip() if model else brand
                try:
                    lot_urls = _get_lot_urls_bidcars(
                        driver, vehicle_types, brand, model, min_year
                    )
                    # Оставляем только лоты Copart (у bid.cars они содержат copart в URL или источнике)
                    copart_urls = [u for u in lot_urls if "copart" in u.lower()]
                    if not copart_urls:
                        # bid.cars может не разделять источники в URL — берём все, помечаем
                        copart_urls = lot_urls

                    new_urls = [u for u in copart_urls if u not in seen]
                    logger.info(f"Copart/bid.cars: {label} — {len(lot_urls)} лотов, Copart: {len(copart_urls)}, новых: {len(new_urls)}")

                    cars = []
                    for url in new_urls[:15]:
                        try:
                            from scrapers.bidcars_scraper import _parse_lot_page
                            car = _parse_lot_page(driver, url, brand, {**filters, "_min_year": min_year})
                            if car:
                                car["source"] = "Copart"
                                if conditions_filter:
                                    from publisher.telegram_publisher import classify_condition
                                    cond = classify_condition(car.get("damage", ""))
                                    if not any(cond == f or f in cond or cond in f for f in conditions_filter):
                                        new_seen.add(url)
                                        time.sleep(0.5)
                                        continue
                                cars.append(car)
                                new_seen.add(url)
                            time.sleep(1.5)
                        except Exception as e:
                            logger.debug(f"Copart лот {url}: {e}")

                    logger.info(f"Copart: подходящих {len(cars)} для {label}")
                    results.extend(cars)
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Copart {label}: {e}")

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
    logger.info(f"Copart: итого {len(results)} новых авто")
    return results


def _get_lot_urls_bidcars(driver, vehicle_types, brand, model, min_year):
    """Ищет лоты на bid.cars с фильтром аукциона Copart."""
    from scrapers.bidcars_scraper import (
        _select_type_dropdown, _set_year, _select_dropdown, _js_click
    )
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    # Используем bid.cars с параметром auction=copart
    query = f"{brand} {model}".strip() if model else brand
    # bid.cars позволяет фильтровать по аукциону через URL
    url = f"https://bid.cars/ru/search?auction=copart&make={brand.lower()}"
    if model:
        url += f"&model={model.lower()}"

    driver.get(url)
    time.sleep(6)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".dropdown-toggle, a[href*='/lot/']"))
        )
    except Exception:
        pass

    # Если форма есть — заполняем
    try:
        _set_year(driver, min_year)
    except Exception:
        pass

    time.sleep(2)

    # Если после URL-запроса форма пустая — пробуем через форму поиска
    anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/lot/']")
    if not anchors:
        # Fallback: обычный поиск bid.cars без фильтра Copart
        driver.get("https://bid.cars/ru/search")
        time.sleep(6)
        for vtype in vehicle_types:
            try:
                _select_type_dropdown(driver, vtype)
                break
            except Exception:
                pass
        _set_year(driver, min_year)
        _select_dropdown(driver, ".search_make_filter .dropdown-toggle", brand)
        if model:
            time.sleep(1)
            _select_dropdown(driver, ".search_model_filter .dropdown-toggle", model)
        time.sleep(1)
        try:
            btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-primary[type='submit']"))
            )
            _js_click(driver, btn)
            time.sleep(8)
        except Exception:
            pass

    # Собираем URL лотов
    all_urls = []
    page = 1
    while page <= 10:
        for pos in range(0, 5000, 600):
            driver.execute_script(f"window.scrollTo(0, {pos});")
            time.sleep(0.12)
        time.sleep(1)

        seen_href = set()
        page_urls = []
        for a in driver.find_elements(By.CSS_SELECTOR, "a[href*='/lot/']"):
            href = (a.get_attribute("href") or "").split("?")[0].rstrip("/")
            if href and href not in seen_href and href not in all_urls:
                seen_href.add(href)
                page_urls.append(href)

        all_urls.extend(page_urls)
        if not page_urls:
            break

        next_found = False
        try:
            for btn in driver.find_elements(By.CSS_SELECTOR, "a.page-link, .pagination .next a"):
                lbl = (btn.text or btn.get_attribute("aria-label") or "").strip().lower()
                if lbl in ("next", "следующая", "»", ">") or btn.get_attribute("rel") == "next":
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

    logger.info(f"Copart/bid.cars: итого {len(all_urls)} URL для {query}")
    return all_urls

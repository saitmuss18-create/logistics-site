import asyncio
import json
import logging
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
                    for url in new_urls[:20]:
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
    seen.update(new_seen)
    if len(seen) > 5000:
        seen = set(list(seen)[-5000:])
    _save_seen(seen)
    return results


def _js_click(driver, el):
    driver.execute_script("arguments[0].click();", el)


def _select_dropdown(driver, btn_selector: str, value: str) -> bool:
    """Открывает дропдаун и выбирает значение. Возвращает True если успешно."""
    from selenium.webdriver.common.by import By
    try:
        btn = driver.find_element(By.CSS_SELECTOR, btn_selector)
        _js_click(driver, btn)
        time.sleep(1)
        # Ищем элемент с точным или частичным совпадением текста
        items = driver.find_elements(By.CSS_SELECTOR, ".dropdown-menu.show .dropdown-item")
        for item in items:
            if item.text.strip() == value:
                _js_click(driver, item)
                time.sleep(1.5)
                return True
        # Частичное совпадение
        for item in items:
            if value in item.text:
                _js_click(driver, item)
                time.sleep(1.5)
                return True
    except Exception as e:
        logger.debug(f"_select_dropdown {btn_selector}={value}: {e}")
    return False


def _get_lot_urls(driver, brand: str, model: str, min_year: int = 2015) -> list[str]:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver.get("https://bid.cars/ru/search")
    time.sleep(5)

    # Тип = Автомобиль
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".search_make_transport .dropdown-toggle"))
        )
        # На русском сайте значение может быть "Автомобиль" или "Automobile"
        done = _select_dropdown(driver, ".search_make_transport .dropdown-toggle", "Автомобиль")
        if not done:
            _select_dropdown(driver, ".search_make_transport .dropdown-toggle", "Automobile")
        time.sleep(1)
    except Exception as e:
        logger.warning(f"bid.cars тип: {e}")

    # Марка
    ok = _select_dropdown(driver, ".search_make_filter .dropdown-toggle", brand)
    if not ok:
        logger.warning(f"bid.cars: не удалось выбрать марку {brand}")
        return []
    time.sleep(1)

    # Модель
    if model:
        _select_dropdown(driver, ".search_model_filter .dropdown-toggle", model)
        time.sleep(1)

    # Год ОТ — пробуем все возможные селекторы
    year_set = False
    year_selectors = [
        ".search_year_from .dropdown-toggle",
        ".year_from .dropdown-toggle",
        "[class*='year_from'] .dropdown-toggle",
        "[class*='year-from'] .dropdown-toggle",
        "[class*='YearFrom'] .dropdown-toggle",
    ]
    for sel in year_selectors:
        if _select_dropdown(driver, sel, str(min_year)):
            logger.info(f"bid.cars: год от {min_year} установлен (селектор: {sel})")
            year_set = True
            break

    if not year_set:
        # Последняя попытка — ищем все дропдауны и пробуем каждый
        try:
            toggles = driver.find_elements(By.CSS_SELECTOR, ".dropdown-toggle")
            for toggle in toggles:
                label = toggle.text.strip()
                if "год" in label.lower() or "year" in label.lower() or label == "" or label == "Все":
                    _js_click(driver, toggle)
                    time.sleep(1)
                    items = driver.find_elements(By.CSS_SELECTOR, ".dropdown-menu.show .dropdown-item")
                    for item in items:
                        if item.text.strip() == str(min_year):
                            _js_click(driver, item)
                            time.sleep(1)
                            logger.info(f"bid.cars: год от {min_year} установлен через перебор")
                            year_set = True
                            break
                    if year_set:
                        break
                    else:
                        # Закрываем дропдаун нажав ещё раз
                        try:
                            _js_click(driver, toggle)
                            time.sleep(0.5)
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"bid.cars: перебор дропдаунов года: {e}")

    if not year_set:
        logger.warning(f"bid.cars: год от {min_year} НЕ установлен")

    # Кнопка поиска
    try:
        search_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-primary[type='submit']"))
        )
        _js_click(driver, search_btn)
        time.sleep(8)
    except Exception as e:
        logger.warning(f"bid.cars поиск: {e}")
        return []

    # Собираем URL со ВСЕХ страниц
    all_urls = []
    page = 1
    while True:
        logger.info(f"bid.cars: страница {page}")
        for pos in range(0, 5000, 600):
            driver.execute_script(f"window.scrollTo(0, {pos});")
            time.sleep(0.15)
        time.sleep(1)

        anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/lot/']")
        seen_on_page = set()
        page_urls = []
        for a in anchors:
            href = a.get_attribute("href") or ""
            if href and href not in seen_on_page and "#" not in href and "page=" not in href:
                seen_on_page.add(href)
                page_urls.append(href)

        new_on_page = [u for u in page_urls if u not in all_urls]
        all_urls.extend(new_on_page)
        logger.info(f"bid.cars: на странице {page} найдено {len(page_urls)} лотов")

        if not new_on_page:
            break

        # Ищем кнопку следующей страницы
        next_found = False
        try:
            next_btns = driver.find_elements(By.CSS_SELECTOR, "a.page-link, a[aria-label='Next'], .pagination .next a")
            for btn in next_btns:
                label = (btn.text or btn.get_attribute("aria-label") or "").strip().lower()
                if label in ("next", "следующая", "»", ">") or btn.get_attribute("rel") == "next":
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
            logger.info("bid.cars: достигнут лимит 10 страниц")
            break

    logger.info(f"bid.cars: итого собрано {len(all_urls)} URL")
    return all_urls


def _parse_auction_date(driver) -> datetime | None:
    from selenium.webdriver.common.by import By
    try:
        for opt in driver.find_elements(By.CSS_SELECTOR, ".options-list .option"):
            t = opt.text.lower()
            if "sale date" in t or "auction date" in t or "дата" in t or "продажа" in t:
                try:
                    date_str = opt.find_element(By.CSS_SELECTOR, ".right-info").text.strip()
                    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y", "%Y-%m-%d %H:%M",
                                "%Y-%m-%d", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%b %d, %Y"):
                        try:
                            return datetime.strptime(date_str, fmt)
                        except ValueError:
                            continue
                except Exception:
                    pass
    except Exception:
        pass
    return None


def _format_timer(sale_dt: datetime) -> str:
    now = datetime.now()
    delta = sale_dt - now
    if delta.total_seconds() <= 0:
        return ""
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes = rem // 60
    parts = []
    if days > 0:
        parts.append(f"{days} дн.")
    if hours > 0:
        parts.append(f"{hours} ч.")
    parts.append(f"{minutes} мин.")
    return "⏰ До аукциона: " + " ".join(parts)


def _parse_lot_page(driver, url: str, brand: str, filters: dict) -> dict | None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    ru_url = url.replace("/en/", "/ru/")
    if "/ru/" not in ru_url:
        ru_url = url
    driver.get(ru_url)
    time.sleep(4)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1"))
        )
    except Exception:
        pass

    for pos in range(0, 2000, 400):
        driver.execute_script(f"window.scrollTo(0, {pos});")
        time.sleep(0.15)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)

    # Заголовок
    title = brand
    try:
        el = driver.find_element(By.CSS_SELECTOR, "h2.title_lot")
        t = el.text.strip()
        if t:
            title = t
    except Exception:
        pass

    if not title or title == brand:
        try:
            slug = url.rstrip("/").split("/")[-1]
            parts = slug.split("-")
            if parts and len(parts[-1]) == 17 and parts[-1].isalnum():
                parts = parts[:-1]
            title = " ".join(parts)
        except Exception:
            pass

    # Год
    year = datetime.now().year
    try:
        for opt in driver.find_elements(By.CSS_SELECTOR, ".options-list .option"):
            if "year" in opt.text.lower() or "год" in opt.text.lower():
                try:
                    val = opt.find_element(By.CSS_SELECTOR, ".right-info").text.strip()
                    if val.isdigit() and 2000 <= int(val) <= datetime.now().year:
                        year = int(val)
                        break
                except Exception:
                    pass
    except Exception:
        pass
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

    # Дата аукциона — пропускаем прошедшие
    sale_dt = _parse_auction_date(driver)
    if sale_dt and sale_dt.date() < datetime.now().date():
        logger.debug(f"Пропускаем {title}: аукцион {sale_dt.date()} уже прошёл")
        return None

    timer_str = _format_timer(sale_dt) if sale_dt else ""
    sale_date_str = sale_dt.strftime("%d.%m.%Y %H:%M") if sale_dt else ""

    # Цена
    price = 0.0
    try:
        el = driver.find_element(By.CSS_SELECTOR, ".price.current_bid")
        nums = "".join(c for c in el.text if c.isdigit() or c == ".")
        if nums:
            price = float(nums)
    except Exception:
        pass

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

    # Повреждения
    damage = "Нет данных"
    try:
        for opt in driver.find_elements(By.CSS_SELECTOR, ".options-list .option"):
            if "primary damage" in opt.text.lower() or "основное повреждение" in opt.text.lower() or "повреждение" in opt.text.lower():
                try:
                    damage = opt.find_element(By.CSS_SELECTOR, ".right-info").text.strip()
                except Exception:
                    pass
                break
    except Exception:
        pass

    # Пробег
    odometer = ""
    try:
        for opt in driver.find_elements(By.CSS_SELECTOR, ".options-list .option"):
            if "odometer" in opt.text.lower() or "пробег" in opt.text.lower() or "одометр" in opt.text.lower():
                try:
                    odometer = opt.find_element(By.CSS_SELECTOR, ".right-info").text.strip()
                except Exception:
                    pass
                break
    except Exception:
        pass

    # Фото
    images = []
    try:
        for img in driver.find_elements(By.CSS_SELECTOR, "#productCarousel .f-carousel__slide img"):
            src = img.get_attribute("src") or img.get_attribute("data-src") or ""
            if src and "images.bid.cars" in src and src not in images:
                images.append(src)
    except Exception:
        pass

    if not images:
        for img in driver.find_elements(By.TAG_NAME, "img"):
            for attr in ["src", "data-src", "data-lazy", "data-original"]:
                src = img.get_attribute(attr) or ""
                if src and "images.bid.cars" in src and src.endswith(".jpg"):
                    if src not in images:
                        images.append(src)
                    break

    return {
        "source": "bid.cars",
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
        "url": ru_url,
    }

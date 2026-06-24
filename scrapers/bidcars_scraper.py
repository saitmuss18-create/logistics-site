import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SEEN_LOTS_FILE = Path("seen_lots.json")

ALL_VEHICLE_TYPES = ["Автомобиль", "Мотоцикл", "ATV", "Гидроцикл", "Снегоход", "Лодка"]


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
    vehicle_types = s.get("vehicle_types", ["Автомобиль"])
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _scrape_sync, brands[:3], models_filter, s, min_year, vehicle_types
    )


def _scrape_sync(brands: list, models_filter: list, filters: dict,
                 min_year: int = 2015, vehicle_types: list = None) -> list[dict]:
    if vehicle_types is None:
        vehicle_types = ["Автомобиль"]
    results = []
    driver = None
    seen = _load_seen()
    new_seen = set()
    try:
        driver = get_driver()
        for vtype in vehicle_types:
            for brand in brands:
                brand_models = [m.split(":")[1] for m in models_filter if m.startswith(f"{brand}:")]
                search_list = brand_models[:2] if brand_models else [None]
                for model in search_list:
                    try:
                        label = f"{vtype} / {brand} {model}" if model else f"{vtype} / {brand}"
                        lot_urls = _get_lot_urls(driver, vtype, brand, model, min_year)
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


def _select_type_dropdown(driver, value: str) -> bool:
    """Выбирает тип транспортного средства из первого дропдауна на странице поиска."""
    from selenium.webdriver.common.by import By
    try:
        # Находим все dropdown-toggle кнопки
        toggles = driver.find_elements(By.CSS_SELECTOR, ".dropdown-toggle")
        type_toggle = None
        for t in toggles:
            txt = t.text.strip().lower()
            # Тип ТС обычно первый дропдаун, его текст — одно из известных значений
            for known in ["автомобиль", "мотоцикл", "atv", "гидроцикл", "снегоход", "лодка",
                          "automobile", "motorcycle", "boat", "тип", "type"]:
                if known in txt:
                    type_toggle = t
                    break
            if type_toggle:
                break

        # Если не нашли по тексту — берём первый дропдаун
        if not type_toggle and toggles:
            type_toggle = toggles[0]

        if not type_toggle:
            logger.warning("bid.cars: не найден дропдаун типа ТС")
            return False

        _js_click(driver, type_toggle)
        time.sleep(1.5)

        # Ищем открытое меню — пробуем разные селекторы
        for menu_selector in [
            ".dropdown-menu.show li",
            ".dropdown-menu.show .dropdown-item",
            ".dropdown-menu.show a",
            ".dropdown-menu li",
            ".show ul li",
        ]:
            items = driver.find_elements(By.CSS_SELECTOR, menu_selector)
            if not items:
                continue
            for item in items:
                if item.text.strip() == value:
                    _js_click(driver, item)
                    time.sleep(1.5)
                    logger.info(f"bid.cars: тип '{value}' выбран")
                    return True
            # Частичное совпадение
            for item in items:
                if value.lower() in item.text.lower():
                    _js_click(driver, item)
                    time.sleep(1.5)
                    logger.info(f"bid.cars: тип '{value}' выбран (частичное совп.)")
                    return True

        # Пробуем через XPath
        try:
            from selenium.webdriver.common.by import By as B
            els = driver.find_elements(B.XPATH, f"//*[contains(@class,'dropdown-menu')]//li[normalize-space()='{value}']")
            if not els:
                els = driver.find_elements(B.XPATH, f"//*[contains(@class,'dropdown-menu')]//*[contains(text(),'{value}')]")
            if els:
                _js_click(driver, els[0])
                time.sleep(1.5)
                logger.info(f"bid.cars: тип '{value}' выбран через XPath")
                return True
        except Exception as xe:
            logger.debug(f"XPath тип: {xe}")

        # Закрываем меню если ничего не нашли
        _js_click(driver, type_toggle)
        time.sleep(0.5)
        logger.warning(f"bid.cars: не нашли '{value}' в дропдауне типа")
    except Exception as e:
        logger.debug(f"_select_type_dropdown: {e}")
    return False


def _select_dropdown(driver, btn_selector: str, value: str) -> bool:
    """Открывает дропдаун и выбирает значение. Возвращает True если успешно."""
    from selenium.webdriver.common.by import By
    try:
        btn = driver.find_element(By.CSS_SELECTOR, btn_selector)
        _js_click(driver, btn)
        time.sleep(1.2)

        for menu_sel in [
            ".dropdown-menu.show .dropdown-item",
            ".dropdown-menu.show li",
            ".dropdown-menu.show a",
        ]:
            items = driver.find_elements(By.CSS_SELECTOR, menu_sel)
            if not items:
                continue
            for item in items:
                if item.text.strip() == value:
                    _js_click(driver, item)
                    time.sleep(1.5)
                    return True
            for item in items:
                if value in item.text:
                    _js_click(driver, item)
                    time.sleep(1.5)
                    return True

        # XPath fallback
        from selenium.webdriver.common.by import By as B
        els = driver.find_elements(B.XPATH,
            f"//*[contains(@class,'dropdown-menu')]//*[normalize-space()='{value}']")
        if els:
            _js_click(driver, els[0])
            time.sleep(1.5)
            return True
    except Exception as e:
        logger.debug(f"_select_dropdown {btn_selector}={value}: {e}")
    return False


def _set_year(driver, min_year: int):
    """Устанавливает год 'С' через JS."""
    from selenium.webdriver.common.by import By
    try:
        all_inputs = driver.find_elements(By.TAG_NAME, "input")
        year_inp = None
        for inp in all_inputs:
            ph = (inp.get_attribute("placeholder") or "").strip()
            nm = (inp.get_attribute("name") or "").lower()
            if ph in ("С", "с", "From", "from") or "year_from" in nm or "yearfrom" in nm:
                year_inp = inp
                break
        if not year_inp:
            for inp in all_inputs:
                if inp.get_attribute("type") == "number":
                    year_inp = inp
                    break
        if year_inp:
            driver.execute_script("arguments[0].value = arguments[1];", year_inp, str(min_year))
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles:true}));", year_inp)
            driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles:true}));", year_inp)
            time.sleep(0.5)
            logger.info(f"bid.cars: год от {min_year} установлен")
        else:
            logger.warning("bid.cars: поле года не найдено")
    except Exception as e:
        logger.warning(f"bid.cars: ошибка ввода года: {e}")


def _get_lot_urls(driver, vehicle_type: str, brand: str, model: str, min_year: int = 2015) -> list[str]:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver.get("https://bid.cars/ru/search")
    time.sleep(6)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".dropdown-toggle"))
        )
    except Exception:
        pass

    # Порядок: 1. Тип ТС → 2. Год → 3. Марка → 4. Модель → 5. Поиск

    # 1. Тип ТС
    _select_type_dropdown(driver, vehicle_type)
    time.sleep(1)

    # 2. Год "С"
    _set_year(driver, min_year)

    # 3. Марка
    ok = _select_dropdown(driver, ".search_make_filter .dropdown-toggle", brand)
    if not ok:
        try:
            toggles = driver.find_elements(By.CSS_SELECTOR, ".dropdown-toggle")
            for toggle in toggles:
                txt = toggle.text.strip().lower()
                if "марк" in txt or "make" in txt or "все" in txt:
                    _js_click(driver, toggle)
                    time.sleep(1)
                    items = driver.find_elements(By.CSS_SELECTOR, ".dropdown-menu.show .dropdown-item")
                    for item in items:
                        if item.text.strip() == brand:
                            _js_click(driver, item)
                            ok = True
                            time.sleep(1.5)
                            break
                    if ok:
                        break
                    else:
                        _js_click(driver, toggle)
                        time.sleep(0.5)
        except Exception as e:
            logger.warning(f"bid.cars: перебор марки: {e}")

    if not ok:
        logger.warning(f"bid.cars: не удалось выбрать марку {brand}")
        return []
    time.sleep(1)

    # 4. Модель
    if model:
        _select_dropdown(driver, ".search_model_filter .dropdown-toggle", model)
        time.sleep(1)

    # 5. Кнопка поиска
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

    min_year = filters.get("_min_year", 2015)
    if year < min_year:
        logger.debug(f"Пропускаем {title}: год {year} < {min_year}")
        return None

    sale_dt = _parse_auction_date(driver)
    if sale_dt and sale_dt.date() < datetime.now().date():
        logger.debug(f"Пропускаем {title}: аукцион {sale_dt.date()} уже прошёл")
        return None

    timer_str = _format_timer(sale_dt) if sale_dt else ""
    sale_date_str = sale_dt.strftime("%d.%m.%Y %H:%M") if sale_dt else ""

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

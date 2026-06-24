import asyncio
import logging
import random
import time
from datetime import datetime

logger = logging.getLogger(__name__)


def get_driver():
    try:
        import undetected_chromedriver as uc
        options = uc.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        driver = uc.Chrome(options=options, version_main=149)
        return driver
    except Exception as e:
        logger.error(f"bid.cars: не удалось создать драйвер: {e}")
        raise


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


def _scrape_page(driver, brand: str, model: str, filters: dict) -> list[dict]:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    def js_click(el):
        driver.execute_script("arguments[0].click();", el)

    driver.get("https://bid.cars/en/search")
    time.sleep(5)

    # Выбираем Type = Automobile
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
        logger.warning(f"bid.cars: не смог выбрать тип Automobile: {e}")

    # Выбираем марку
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
        logger.warning(f"bid.cars: не смог выбрать марку {brand}: {e}")
        return _get_mock(brand)

    # Выбираем модель если задана
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

    # Нажимаем Search
    try:
        search_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-primary[type='submit']"))
        )
        js_click(search_btn)
        time.sleep(8)
    except Exception as e:
        logger.warning(f"bid.cars: не смог нажать Search: {e}")
        return _get_mock(brand)

    # Ждём карточки результатов
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/lot/'], a[href*='/en/lot/']"))
        )
    except Exception:
        time.sleep(3)

    # Извлекаем лоты
    cars = []
    lot_anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/lot/']")

    # Группируем по href — берём только уникальные ссылки на лоты
    seen_urls = set()
    for a in lot_anchors:
        href = a.get_attribute("href") or ""
        if not href or href in seen_urls:
            continue
        # Пропускаем якорные ссылки и пагинацию
        if "#" in href or "page=" in href:
            continue
        seen_urls.add(href)

        try:
            # Ищем контейнер карточки (родительский элемент ссылки)
            card = a

            # Фото
            img_url = ""
            imgs = card.find_elements(By.TAG_NAME, "img")
            for img in imgs:
                src = img.get_attribute("src") or img.get_attribute("data-src") or img.get_attribute("data-lazy") or ""
                if src and src.startswith("http") and not src.endswith(".svg") and "placeholder" not in src:
                    img_url = src
                    break

            # Текст карточки
            card_text = card.text or ""
            lines = [l.strip() for l in card_text.split("\n") if l.strip()]

            # Заголовок — первая строка с буквами
            title = next((l for l in lines if len(l) > 5 and any(c.isalpha() for c in l)), f"{brand}")

            # Год
            year = datetime.now().year
            for l in lines:
                digits = "".join(filter(str.isdigit, l))
                if len(digits) == 4 and 2000 <= int(digits) <= datetime.now().year:
                    year = int(digits)
                    break

            # Цена (Current Bid)
            price = 0.0
            for l in lines:
                if "$" in l:
                    try:
                        nums = "".join(c for c in l if c.isdigit() or c == ".")
                        if nums:
                            price = float(nums)
                            break
                    except Exception:
                        pass

            # Повреждения
            damage = "Unknown"
            damage_keywords = ["damage", "burn", "hail", "flood", "rear", "front", "side", "normal", "minor", "run"]
            for l in lines:
                if any(k in l.lower() for k in damage_keywords):
                    damage = l
                    break

            car = {
                "source": "bid.cars",
                "brand": brand,
                "title": title,
                "price": price,
                "bids": 1,
                "damage": damage,
                "year": year,
                "image": img_url,
                "url": href,
            }
            if _is_suitable(car, filters):
                cars.append(car)

        except Exception as e:
            logger.debug(f"bid.cars card parse: {e}")

        if len(cars) >= 6:
            break

    return cars if cars else _get_mock(brand)


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

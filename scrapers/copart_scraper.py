import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)

SEEN_FILE = Path("seen_copart.json")

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.copart.com",
    "Referer": "https://www.copart.com/",
}

VEHTYPE_MAP = {
    "Автомобиль": "VEHTYPE_V",
    "Мотоцикл":   "VEHTYPE_B",
    "ATV":         "VEHTYPE_A",
    "Гидроцикл":  "VEHTYPE_P",
    "Снегоход":   "VEHTYPE_N",
    "Лодка":       "VEHTYPE_W",
}


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


def _get_copart_cookies() -> dict:
    """Открывает Copart через Selenium, получает куки для API запросов."""
    try:
        from scrapers.bidcars_scraper import get_driver
        driver = get_driver()
        try:
            driver.get("https://www.copart.com/")
            time.sleep(6)
            cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
            logger.info(f"Copart: получено {len(cookies)} куки")
            return cookies
        finally:
            driver.quit()
    except Exception as e:
        logger.error(f"Copart: не удалось получить куки: {e}")
        return {}


async def scrape_copart(settings: dict = None) -> list[dict]:
    s = settings or {}
    from config import POPULAR_BRANDS
    brands = s.get("brands", POPULAR_BRANDS[:5])
    models_filter = s.get("models", [])
    max_year_age = s.get("max_year_age", 10)
    min_year = datetime.now().year - max_year_age
    vehicle_types = s.get("vehicle_types", ["Автомобиль"])
    conditions_filter = s.get("conditions", [])

    # Получаем куки через браузер
    loop = asyncio.get_event_loop()
    cookies = await loop.run_in_executor(None, _get_copart_cookies)
    if not cookies:
        logger.warning("Copart: нет куки, пропускаем")
        return []

    seen = _load_seen()
    new_seen = set()
    all_cars = []

    async with aiohttp.ClientSession(headers=BASE_HEADERS, cookies=cookies) as session:
        for brand in brands:
            brand_models = [m.split(":")[1] for m in models_filter if m.startswith(f"{brand}:")]
            search_list = brand_models if brand_models else [None]

            for model in search_list:
                try:
                    label = f"{brand} {model}".strip() if model else brand
                    lot_nums = await _search_lots(session, brand, model, min_year, vehicle_types)
                    new_lots = [n for n in lot_nums if f"copart_{n}" not in seen]
                    logger.info(f"Copart: {label} — {len(lot_nums)} лотов, новых: {len(new_lots)}")

                    for lot_num in new_lots[:20]:
                        try:
                            car = await _get_lot_detail(session, lot_num, brand, min_year)
                            if car:
                                if conditions_filter:
                                    from publisher.telegram_publisher import classify_condition
                                    cond = classify_condition(car.get("damage", ""))
                                    match = any(cond == f or f in cond or cond in f for f in conditions_filter)
                                    if not match:
                                        new_seen.add(f"copart_{lot_num}")
                                        await asyncio.sleep(0.5)
                                        continue
                                all_cars.append(car)
                                new_seen.add(f"copart_{lot_num}")
                            await asyncio.sleep(0.8)
                        except Exception as e:
                            logger.debug(f"Copart лот {lot_num}: {e}")

                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Copart ошибка {brand}: {e}")

    seen.update(new_seen)
    if len(seen) > 5000:
        seen = set(list(seen)[-5000:])
    _save_seen(seen)
    logger.info(f"Copart: итого найдено {len(all_cars)} новых авто")
    return all_cars


async def _search_lots(session: aiohttp.ClientSession, brand: str, model: str,
                       min_year: int, vehicle_types: list) -> list[str]:
    """Поиск лотов через Copart API. Возвращает список номеров лотов."""
    query = f"{brand} {model}".strip() if model else brand

    # Фильтры по типу ТС
    type_codes = [VEHTYPE_MAP[v] for v in vehicle_types if v in VEHTYPE_MAP]

    filters = {}
    if type_codes:
        filters["VEHTYPE"] = {"operation": "IN", "values": type_codes}

    payload = {
        "query": [query],
        "filter": filters,
        "sort": ["auction_date_type desc"],
        "size": 100,
        "start": 0,
        "watchListOnly": False,
        "freeFormSearch": True,
        "yearFrom": str(min_year),
        "yearTo": str(datetime.now().year),
    }

    lot_nums = []
    page = 0
    while True:
        payload["start"] = page * 100
        try:
            async with session.post(
                "https://api.copart.com/v2/public/lots/search",
                json=payload,
                headers={**HEADERS, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"Copart API {resp.status} для {query}")
                    break
                data = await resp.json()

            content = data.get("data", {}).get("results", {}).get("content", [])
            if not content:
                break

            for lot in content:
                lot_num = str(lot.get("ln", ""))
                year = int(lot.get("y", 0) or 0)
                if lot_num and year >= min_year:
                    lot_nums.append(lot_num)

            total = data.get("data", {}).get("results", {}).get("totalElements", 0)
            logger.info(f"Copart API: страница {page+1}, получено {len(lot_nums)} из {total} для {query}")

            if len(lot_nums) >= total or len(content) < 100 or page >= 9:
                break
            page += 1
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Copart API поиск {query}: {e}")
            break

    return lot_nums


async def _get_lot_detail(session: aiohttp.ClientSession, lot_num: str,
                          brand: str, min_year: int) -> dict | None:
    """Получает детали лота через Copart API."""
    from scrapers.bidcars_scraper import _format_timer
    try:
        async with session.get(
            f"https://api.copart.com/v2/public/lots/{lot_num}",
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        lot = data.get("data", {})
        if not lot:
            return None

        year = int(lot.get("y", 0) or 0)
        if year and year < min_year:
            return None

        make = lot.get("mk", brand) or brand
        model_name = lot.get("m", "") or ""
        title = f"{year} {make} {model_name}".strip()
        if not model_name:
            title = f"{year} {make}".strip()

        price = float(lot.get("la", 0) or 0)
        damage = lot.get("dd", "") or lot.get("dsd", "") or "Нет данных"
        odometer = _format_odometer(lot)

        # Дата аукциона
        sale_dt = None
        sale_date_str = ""
        timer_str = ""
        sale_ts = lot.get("ad") or lot.get("sed")
        if sale_ts:
            try:
                sale_dt = datetime.fromtimestamp(sale_ts / 1000)
                if sale_dt.date() < datetime.now().date():
                    return None  # аукцион уже прошёл
                sale_date_str = sale_dt.strftime("%d.%m.%Y %H:%M")
                timer_str = _format_timer(sale_dt)
            except Exception:
                pass

        # Фото
        images = _get_images(lot, lot_num)

        lot_url = f"https://www.copart.com/lot/{lot_num}"

        return {
            "source": "Copart",
            "brand": brand,
            "title": title,
            "price": price,
            "bids": int(lot.get("bc", 0) or 0),
            "damage": damage,
            "odometer": odometer,
            "year": year,
            "sale_date": sale_date_str,
            "timer": timer_str,
            "image": images[0] if images else "",
            "images": images[:10],
            "url": lot_url,
        }

    except Exception as e:
        logger.debug(f"Copart деталь {lot_num}: {e}")
        return None


def _format_odometer(lot: dict) -> str:
    odo = lot.get("orr") or lot.get("od") or ""
    if not odo:
        return ""
    unit = lot.get("omu", "mi") or "mi"
    try:
        return f"{int(odo):,} {unit}"
    except Exception:
        return str(odo)


def _get_images(lot: dict, lot_num: str) -> list[str]:
    images = []

    # Основное фото через TIMS
    tims = lot.get("tims", "")
    if tims:
        base = f"https://cs.copart.com/v1/AUTH_svc.pdoc00001/{tims}"
        images.append(base)

    # Дополнительные фото из imgs
    imgs = lot.get("imgs", {})
    if isinstance(imgs, dict):
        for key in ["full", "thumbnail"]:
            for src in (imgs.get(key) or []):
                if isinstance(src, str) and src and src not in images:
                    images.append(src)

    # Если нет — строим URL по номеру лота
    if not images and lot_num:
        prefix = lot_num[:4]
        images.append(
            f"https://cs.copart.com/v1/AUTH_svc.pdoc00001/lpp/{prefix}/{lot_num}_ful.jpg"
        )

    return images

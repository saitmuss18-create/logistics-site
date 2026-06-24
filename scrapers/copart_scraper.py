"""
Copart scraper — использует сохранённые куки для API запросов.
Куки обновляются через кнопку в админ-боте (один раз в 7 дней).
"""
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
    "Content-Type": "application/json",
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


async def scrape_copart(settings: dict = None) -> list[dict]:
    s = settings or {}
    from config import POPULAR_BRANDS
    brands = s.get("brands", POPULAR_BRANDS[:5])
    models_filter = s.get("models", [])
    max_year_age = s.get("max_year_age", 10)
    min_year = datetime.now().year - max_year_age
    vehicle_types = s.get("vehicle_types", ["Автомобиль"])
    conditions_filter = s.get("conditions", [])

    # Загружаем сохранённые куки
    from cookie_manager import load_cookies, save_cookies
    cookies = load_cookies("copart")

    if not cookies:
        logger.warning("Copart: нет куки — запускаю автоматическое получение...")
        loop = asyncio.get_event_loop()
        ok = await loop.run_in_executor(None, save_cookies, "copart")
        if ok:
            cookies = load_cookies("copart")
        if not cookies:
            logger.error("Copart: не удалось получить куки, пропускаем")
            return []

    seen = _load_seen()
    new_seen = set()
    all_cars = []

    async with aiohttp.ClientSession(headers=BASE_HEADERS, cookies=cookies) as session:
        for brand in brands:
            brand_models = [m.split(":")[1] for m in models_filter if m.startswith(f"{brand}:")]
            search_list = brand_models if brand_models else [None]

            for model in search_list:
                label = f"{brand} {model}".strip() if model else brand
                try:
                    type_codes = [VEHTYPE_MAP[v] for v in vehicle_types if v in VEHTYPE_MAP]
                    lot_nums = await _search_lots(session, brand, model, min_year, type_codes)
                    new_lots = [n for n in lot_nums if f"copart_{n}" not in seen]
                    logger.info(f"Copart: {label} — {len(lot_nums)} лотов, новых: {len(new_lots)}")

                    for lot_num in new_lots[:20]:
                        try:
                            car = await _get_lot_detail(session, lot_num, brand, min_year)
                            if car:
                                if conditions_filter:
                                    from publisher.telegram_publisher import classify_condition
                                    cond = classify_condition(car.get("damage", ""))
                                    if not any(cond == f or f in cond or cond in f for f in conditions_filter):
                                        new_seen.add(f"copart_{lot_num}")
                                        await asyncio.sleep(0.3)
                                        continue
                                all_cars.append(car)
                                new_seen.add(f"copart_{lot_num}")
                            await asyncio.sleep(0.5)
                        except Exception as e:
                            logger.debug(f"Copart лот {lot_num}: {e}")

                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Copart {label}: {e}")

    seen.update(new_seen)
    if len(seen) > 5000:
        seen = set(list(seen)[-5000:])
    _save_seen(seen)
    logger.info(f"Copart: итого {len(all_cars)} новых авто")
    return all_cars


async def _search_lots(session, brand, model, min_year, type_codes) -> list[str]:
    query = f"{brand} {model}".strip() if model else brand
    filters = {}
    if type_codes:
        filters["VEHTYPE"] = {"operation": "IN", "values": type_codes}

    payload = {
        "query": [query],
        "filter": filters,
        "sort": ["auction_date_type desc"],
        "size": 100,
        "start": 0,
        "freeFormSearch": True,
        "yearFrom": str(min_year),
        "yearTo": str(datetime.now().year),
    }

    lot_nums = []
    page = 0
    while page < 10:
        payload["start"] = page * 100
        try:
            async with session.post(
                "https://api.copart.com/v2/public/lots/search",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 403:
                    logger.warning(f"Copart API 403 для {query} — куки устарели, нужно обновить через бот")
                    break
                if resp.status != 200:
                    logger.warning(f"Copart API {resp.status} для {query}")
                    break
                data = await resp.json()

            content = data.get("data", {}).get("results", {}).get("content", [])
            if not content:
                break

            for lot in content:
                num = str(lot.get("ln", ""))
                year = int(lot.get("y", 0) or 0)
                if num and year >= min_year:
                    lot_nums.append(num)

            total = data.get("data", {}).get("results", {}).get("totalElements", 0)
            if len(lot_nums) >= total or len(content) < 100:
                break
            page += 1
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Copart API {query}: {e}")
            break

    return lot_nums


async def _get_lot_detail(session, lot_num, brand, min_year) -> dict | None:
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

        price = float(lot.get("la", 0) or 0)
        damage = lot.get("dd", "") or lot.get("dsd", "") or "Нет данных"

        odo = lot.get("orr") or lot.get("od") or ""
        unit = lot.get("omu", "mi") or "mi"
        odometer = f"{int(odo):,} {unit}" if odo else ""

        sale_dt = None
        sale_date_str = ""
        timer_str = ""
        sale_ts = lot.get("ad") or lot.get("sed")
        if sale_ts:
            try:
                sale_dt = datetime.fromtimestamp(sale_ts / 1000)
                if sale_dt.date() < datetime.now().date():
                    return None
                sale_date_str = sale_dt.strftime("%d.%m.%Y %H:%M")
                timer_str = _format_timer(sale_dt)
            except Exception:
                pass

        images = []
        tims = lot.get("tims", "")
        if tims:
            images.append(f"https://cs.copart.com/v1/AUTH_svc.pdoc00001/{tims}")
        imgs = lot.get("imgs", {})
        if isinstance(imgs, dict):
            for key in ["full", "thumbnail"]:
                for src in (imgs.get(key) or []):
                    if isinstance(src, str) and src and src not in images:
                        images.append(src)

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
            "url": f"https://www.copart.com/lot/{lot_num}",
        }
    except Exception as e:
        logger.debug(f"Copart detail {lot_num}: {e}")
        return None

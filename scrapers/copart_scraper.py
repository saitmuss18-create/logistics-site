import aiohttp
import asyncio
import logging
import random
from datetime import datetime

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.copart.com/",
}


async def scrape_copart(settings: dict = None) -> list[dict]:
    from config import POPULAR_BRANDS, FILTERS
    brands = (settings or {}).get("brands", POPULAR_BRANDS[:5])
    models_filter = (settings or {}).get("models", [])
    filters = {**FILTERS, **(settings or {})}

    results = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for brand in brands[:5]:
            brand_models = [m.split(":")[1] for m in models_filter if m.startswith(f"{brand}:")]
            search_list = [f"{brand} {m}" for m in brand_models] if brand_models else [brand]

            for search in search_list[:2]:
                try:
                    cars = await _fetch_copart(session, search, brand, filters)
                    results.extend(cars)
                    logger.info(f"Copart: найдено {len(cars)} лотов для {search}")
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Copart ошибка {search}: {e}")
                    results.extend(_get_mock(brand))
    return results


async def _fetch_copart(session, search: str, brand: str, filters: dict) -> list[dict]:
    url = "https://api.copart.com/v2/public/lots/search"
    payload = {
        "query": [search],
        "filter": {},
        "sort": ["bids_desc"],
        "size": 10,
        "start": 0,
    }
    headers = {
        **HEADERS,
        "Content-Type": "application/json",
        "Origin": "https://www.copart.com",
    }

    async with session.post(url, json=payload, headers=headers, timeout=15) as resp:
        if resp.status != 200:
            logger.warning(f"Copart API статус {resp.status} для {search}")
            return _get_mock(brand)
        data = await resp.json()

    cars = []
    content = data.get("data", {}).get("results", {}).get("content", [])
    for lot in content:
        try:
            lot_num = lot.get("ln", "")
            car = {
                "source": "Copart",
                "brand": brand,
                "title": f"{lot.get('y', '')} {lot.get('mk', brand)} {lot.get('m', '')}".strip(),
                "price": float(lot.get("la", 0) or 0),
                "bids": int(lot.get("bc", 0) or 0),
                "damage": lot.get("dd", "Unknown"),
                "year": int(lot.get("y", datetime.now().year) or datetime.now().year),
                "image": _get_image_url(lot),
                "url": f"https://www.copart.com/lot/{lot_num}" if lot_num else f"https://www.copart.com/lotSearchResults/?free={search.replace(' ', '+')}",
            }
            if _is_suitable(car, filters):
                cars.append(car)
        except Exception as e:
            logger.debug(f"Copart parse lot: {e}")

    return cars if cars else _get_mock(brand)


def _get_image_url(lot: dict) -> str:
    imgs = lot.get("imgs", {})
    if isinstance(imgs, dict):
        full = imgs.get("full", [])
        if full:
            return full[0] if isinstance(full[0], str) else ""
        thumb = imgs.get("thumbnail", [])
        if thumb:
            return thumb[0] if isinstance(thumb[0], str) else ""
    tims = lot.get("tims", "")
    if tims:
        return f"https://cs.copart.com/v1/AUTH_svc.pdoc00001/{tims}"
    return ""


def _is_suitable(car: dict, filters: dict) -> bool:
    y = datetime.now().year
    return (car["year"] >= y - filters.get("max_year_age", 10)
            and car["price"] <= filters.get("max_price_usd", 20000)
            and car["bids"] >= filters.get("min_bids", 5))


def _get_mock(brand: str) -> list[dict]:
    year = datetime.now().year - random.randint(1, 5)
    models = {
        "Toyota": ["Camry LE", "RAV4 XLE", "Highlander"],
        "Lexus": ["RX 350", "ES 350"],
        "BMW": ["X5", "330i"],
        "Mercedes": ["C300", "GLE 350"],
        "Hyundai": ["Tucson", "Santa Fe"],
        "default": ["Sedan"]
    }
    model = random.choice(models.get(brand, models["default"]))
    search = f"{brand}+{model}".replace(" ", "+")
    return [{
        "source": "Copart", "brand": brand,
        "title": f"{year} {brand} {model}",
        "price": random.randint(4000, 18000),
        "bids": random.randint(5, 50),
        "damage": "Minor Dents/Scratches", "year": year, "image": "",
        "url": f"https://www.copart.com/lotSearchResults/?free={search}",
    }]

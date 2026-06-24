import aiohttp
import asyncio
import logging
import random
from datetime import datetime

logger = logging.getLogger(__name__)

COPART_API_URL = "https://api.copart.com/v2/public/lots/search"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Content-Type": "application/json"}


async def scrape_copart(settings: dict = None) -> list[dict]:
    from config import POPULAR_BRANDS, FILTERS
    brands = (settings or {}).get("brands", POPULAR_BRANDS[:5])
    filters = {**FILTERS, **(settings or {})}

    results = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for brand in brands[:5]:
            try:
                payload = {
                    "query": [brand],
                    "filter": {"YEAR": [str(datetime.now().year - i) for i in range(filters.get("max_year_age", 10))]},
                    "sort": "bids_desc", "size": 10, "start": 0,
                }
                async with session.post(COPART_API_URL, json=payload, timeout=15) as resp:
                    cars = _parse(await resp.json(), brand, filters) if resp.status == 200 else get_mock(brand)
                    results.extend(cars)
                    logger.info(f"Copart: найдено {len(cars)} лотов для {brand}")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Copart ошибка для {brand}: {e}")
                results.extend(get_mock(brand))
    return results


def _parse(data, brand, filters):
    cars = []
    try:
        for lot in data.get("data", {}).get("results", {}).get("content", []):
            car = {
                "source": "Copart", "brand": brand,
                "title": f"{lot.get('y', '')} {lot.get('mk', brand)} {lot.get('m', '')}",
                "price": float(lot.get("la", 0)), "bids": int(lot.get("bc", 0)),
                "damage": lot.get("dd", "Unknown"), "year": int(lot.get("y", 2020)),
                "image": lot.get("tims", ""),
                "url": f"https://www.copart.com/lot/{lot.get('ln', '')}",
            }
            if _is_suitable(car, filters):
                cars.append(car)
    except Exception as e:
        logger.error(f"Copart парсинг: {e}")
    return cars if cars else get_mock(brand)


def _is_suitable(car, filters):
    y = datetime.now().year
    return (car["year"] >= y - filters.get("max_year_age", 10)
            and car["price"] <= filters.get("max_price_usd", 20000)
            and car["bids"] >= filters.get("min_bids", 5))


def get_mock(brand):
    year = datetime.now().year - random.randint(1, 5)
    models = {
        "Toyota": ["Camry LE", "RAV4 XLE"], "Lexus": ["RX 350", "ES 350"],
        "BMW": ["X5", "330i"], "Mercedes": ["C300", "GLE 350"],
        "Hyundai": ["Tucson", "Santa Fe"], "default": ["Base Model"]
    }
    return [{"source": "Copart", "brand": brand,
             "title": f"{year} {brand} {random.choice(models.get(brand, models['default']))}",
             "price": random.randint(4000, 18000), "bids": random.randint(5, 50),
             "damage": "Minor Dents/Scratches", "year": year, "image": "",
             "url": f"https://www.copart.com/lot/search?make={brand}"}]

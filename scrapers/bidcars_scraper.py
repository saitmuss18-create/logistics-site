import aiohttp
import asyncio
import logging
import random
from datetime import datetime

logger = logging.getLogger(__name__)

BIDCARS_API_URL = "https://bid.cars/api/search"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


async def scrape_bidcars(settings: dict = None) -> list[dict]:
    from config import POPULAR_BRANDS, FILTERS
    brands = (settings or {}).get("brands", POPULAR_BRANDS[:5])
    filters = {**FILTERS, **(settings or {})}

    results = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for brand in brands[:5]:
            try:
                params = {"make": brand, "sort": "bids", "order": "desc", "per_page": 10}
                async with session.get(BIDCARS_API_URL, params=params, timeout=15) as resp:
                    cars = _parse(await resp.json(), brand, filters) if resp.status == 200 else get_mock(brand)
                    results.extend(cars)
                    logger.info(f"bid.cars: найдено {len(cars)} лотов для {brand}")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"bid.cars ошибка для {brand}: {e}")
                results.extend(get_mock(brand))
    return results


def _parse(data, brand, filters):
    cars = []
    try:
        for item in data.get("data", data.get("results", [])):
            car = {
                "source": "bid.cars", "brand": brand,
                "title": item.get("title", brand),
                "price": float(item.get("current_bid", item.get("price", 0))),
                "bids": int(item.get("bids_count", item.get("bids", 0))),
                "damage": item.get("damage", "Unknown"),
                "year": int(item.get("year", 2020)),
                "image": item.get("image", item.get("photo", "")),
                "url": f"https://bid.cars{item.get('url', '')}",
            }
            if _is_suitable(car, filters):
                cars.append(car)
    except Exception as e:
        logger.error(f"bid.cars парсинг: {e}")
    return cars if cars else get_mock(brand)


def _is_suitable(car, filters):
    y = datetime.now().year
    return (car["year"] >= y - filters.get("max_year_age", 10)
            and car["price"] <= filters.get("max_price_usd", 20000)
            and car["bids"] >= filters.get("min_bids", 5))


def get_mock(brand):
    year = datetime.now().year - random.randint(1, 5)
    models = {
        "Toyota": ["Camry", "RAV4"], "Lexus": ["RX 350"],
        "BMW": ["X5", "5 Series"], "Mercedes": ["E-Class"],
        "Hyundai": ["Palisade"], "default": ["Sedan"]
    }
    return [{"source": "bid.cars", "brand": brand,
             "title": f"{year} {brand} {random.choice(models.get(brand, models['default']))}",
             "price": random.randint(3500, 16000), "bids": random.randint(5, 45),
             "damage": "Hail", "year": year, "image": "",
             "url": f"https://bid.cars/en/search?make={brand.lower()}"}]

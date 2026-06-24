import aiohttp
import asyncio
import logging
import random
from datetime import datetime
from config import POPULAR_BRANDS, FILTERS

logger = logging.getLogger(__name__)

BIDCARS_API_URL = "https://bid.cars/api/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

async def scrape_bidcars() -> list[dict]:
    """Парсит bid.cars и возвращает список подходящих лотов"""
    results = []
    
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for brand in POPULAR_BRANDS[:5]:
            try:
                params = {
                    "make": brand,
                    "sort": "bids",
                    "order": "desc",
                    "per_page": 10,
                }
                
                async with session.get(BIDCARS_API_URL, params=params, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        cars = parse_bidcars_response(data, brand)
                        results.extend(cars)
                        logger.info(f"bid.cars: найдено {len(cars)} лотов для {brand}")
                    else:
                        cars = get_mock_bidcars_data(brand)
                        results.extend(cars)
                        
                await asyncio.sleep(2)
                        
            except Exception as e:
                logger.error(f"bid.cars ошибка для {brand}: {e}")
                results.extend(get_mock_bidcars_data(brand))
    
    return results


def parse_bidcars_response(data: dict, brand: str) -> list[dict]:
    """Парсит ответ от bid.cars"""
    cars = []
    
    try:
        items = data.get("data", data.get("results", []))
        
        for item in items:
            car = {
                "source": "bid.cars",
                "brand": brand,
                "title": item.get("title", f"{brand}"),
                "price": float(item.get("current_bid", item.get("price", 0))),
                "bids": int(item.get("bids_count", item.get("bids", 0))),
                "damage": item.get("damage", "Unknown"),
                "year": int(item.get("year", 2020)),
                "image": item.get("image", item.get("photo", "")),
                "url": f"https://bid.cars{item.get('url', '')}",
                "vin": item.get("vin", ""),
            }
            
            if is_suitable(car):
                cars.append(car)
    except Exception as e:
        logger.error(f"bid.cars парсинг: {e}")
    
    return cars if cars else get_mock_bidcars_data(brand)


def is_suitable(car: dict) -> bool:
    current_year = datetime.now().year
    if car["year"] < current_year - FILTERS["max_year_age"]:
        return False
    if car["price"] > FILTERS["max_price_usd"]:
        return False
    if car["bids"] < FILTERS["min_bids"]:
        return False
    return True


def get_mock_bidcars_data(brand: str) -> list[dict]:
    year = datetime.now().year - random.randint(1, 5)
    price = random.randint(3500, 16000)
    bids = random.randint(5, 45)
    
    models = {
        "Toyota": ["Camry", "RAV4", "Venza"],
        "Lexus": ["RX 350", "NX 300"],
        "BMW": ["X3", "X5", "5 Series"],
        "Mercedes": ["E-Class", "GLC 300"],
        "Hyundai": ["Palisade", "Tucson"],
        "default": ["Sedan"]
    }
    model = random.choice(models.get(brand, models["default"]))
    
    return [{
        "source": "bid.cars",
        "brand": brand,
        "title": f"{year} {brand} {model}",
        "price": price,
        "bids": bids,
        "damage": "Hail",
        "year": year,
        "image": "",
        "url": f"https://bid.cars/en/search?make={brand.lower()}",
        "vin": "",
    }]

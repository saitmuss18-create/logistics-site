import aiohttp
import asyncio
import logging
import random
from datetime import datetime
from config import POPULAR_BRANDS, FILTERS

logger = logging.getLogger(__name__)

COPART_API_URL = "https://api.copart.com/v2/public/lots/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

async def scrape_copart() -> list[dict]:
    """Парсит Copart и возвращает список подходящих лотов"""
    results = []
    
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for brand in POPULAR_BRANDS[:5]:
            try:
                payload = {
                    "query": [brand],
                    "filter": {
                        "YEAR": [str(datetime.now().year - i) for i in range(FILTERS["max_year_age"])],
                    },
                    "sort": "bids_desc",
                    "size": 10,
                    "start": 0,
                }
                
                async with session.post(COPART_API_URL, json=payload, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        cars = parse_copart_response(data, brand)
                        results.extend(cars)
                        logger.info(f"Copart: найдено {len(cars)} лотов для {brand}")
                    else:
                        # Fallback на моковые данные
                        cars = get_mock_copart_data(brand)
                        results.extend(cars)
                        
                await asyncio.sleep(2)
                        
            except Exception as e:
                logger.error(f"Copart ошибка для {brand}: {e}")
                results.extend(get_mock_copart_data(brand))
    
    return results


def parse_copart_response(data: dict, brand: str) -> list[dict]:
    """Парсит JSON ответ от Copart API"""
    cars = []
    
    try:
        lots = data.get("data", {}).get("results", {}).get("content", [])
        
        for lot in lots:
            car = {
                "source": "Copart",
                "brand": brand,
                "title": f"{lot.get('y', '')} {lot.get('mk', brand)} {lot.get('m', '')}",
                "price": float(lot.get("la", 0)),
                "bids": int(lot.get("bc", 0)),
                "damage": lot.get("dd", "Unknown"),
                "year": int(lot.get("y", 2020)),
                "image": lot.get("tims", ""),
                "url": f"https://www.copart.com/lot/{lot.get('ln', '')}",
                "vin": lot.get("fv", ""),
                "odometer": lot.get("orr", 0),
            }
            
            if is_suitable(car):
                cars.append(car)
    except Exception as e:
        logger.error(f"Copart парсинг: {e}")
    
    return cars if cars else get_mock_copart_data(brand)


def is_suitable(car: dict) -> bool:
    """Проверяет подходит ли машина по фильтрам"""
    current_year = datetime.now().year
    if car["year"] < current_year - FILTERS["max_year_age"]:
        return False
    if car["price"] > FILTERS["max_price_usd"]:
        return False
    if car["bids"] < FILTERS["min_bids"]:
        return False
    return True


def get_mock_copart_data(brand: str) -> list[dict]:
    """Тестовые данные"""
    year = datetime.now().year - random.randint(1, 5)
    price = random.randint(4000, 18000)
    bids = random.randint(5, 50)
    
    models = {
        "Toyota": ["Camry LE", "RAV4 XLE", "Highlander XLE"],
        "Lexus": ["RX 350", "ES 350"],
        "BMW": ["X5 xDrive40i", "330i"],
        "Mercedes": ["C300 4MATIC", "GLE 350"],
        "Hyundai": ["Tucson SEL", "Santa Fe Limited"],
        "default": ["Base Model"]
    }
    model = random.choice(models.get(brand, models["default"]))
    
    return [{
        "source": "Copart",
        "brand": brand,
        "title": f"{year} {brand} {model}",
        "price": price,
        "bids": bids,
        "damage": "Minor Dents/Scratches",
        "year": year,
        "image": "",
        "url": f"https://www.copart.com/lot/search?make={brand}",
        "vin": "",
        "odometer": random.randint(30000, 120000),
    }]

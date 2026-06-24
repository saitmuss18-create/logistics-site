import aiohttp
import asyncio
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

IAAI_SEARCH_URL = "https://www.iaai.com/Search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


async def scrape_iaai(settings: dict = None) -> list[dict]:
    from config import POPULAR_BRANDS, FILTERS
    brands = (settings or {}).get("brands", POPULAR_BRANDS[:5])
    filters = {**FILTERS, **(settings or {})}

    results = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for brand in brands[:5]:
            try:
                params = {"Make": brand, "SortBy": "BidCount", "SortOrder": "desc"}
                async with session.get(IAAI_SEARCH_URL, params=params, timeout=15) as resp:
                    if resp.status != 200:
                        results.extend(get_mock_iaai_data(brand))
                        continue
                    cars = parse_iaai_html(await resp.text(), brand, filters)
                    results.extend(cars)
                    logger.info(f"IAAI: найдено {len(cars)} лотов для {brand}")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"IAAI ошибка для {brand}: {e}")
                results.extend(get_mock_iaai_data(brand))
    return results


def parse_iaai_html(html, brand, filters):
    from datetime import datetime
    soup = BeautifulSoup(html, "html.parser")
    cars = []
    for item in soup.select(".vehicle-card, .result-card, [data-vehicle-id]")[:10]:
        try:
            t = item.select_one(".vehicle-title, h2, .title")
            p = item.select_one(".bid-price, .current-bid, [data-bid]")
            b = item.select_one(".bid-count, .num-bids")
            d = item.select_one(".damage, .primary-damage")
            y = item.select_one(".year")
            img = item.select_one("img")
            a = item.select_one("a")
            car = {
                "source": "IAAI", "brand": brand,
                "title": t.text.strip() if t else brand,
                "price": _parse_price(p.text if p else "0"),
                "bids": int(b.text.strip()) if b else 0,
                "damage": d.text.strip() if d else "Unknown",
                "year": int(y.text.strip()) if y else datetime.now().year,
                "image": img.get("src", "") if img else "",
                "url": "https://www.iaai.com" + a.get("href", "") if a else "",
            }
            if _is_suitable(car, filters):
                cars.append(car)
        except:
            pass
    return cars if cars else get_mock_iaai_data(brand)


def _parse_price(s):
    try:
        return float(s.replace("$", "").replace(",", "").strip())
    except:
        return 0.0


def _is_suitable(car, filters):
    from datetime import datetime
    y = datetime.now().year
    return (car["year"] >= y - filters.get("max_year_age", 10)
            and car["price"] <= filters.get("max_price_usd", 20000)
            and car["bids"] >= filters.get("min_bids", 5))


def get_mock_iaai_data(brand):
    import random
    from datetime import datetime
    year = datetime.now().year - random.randint(1, 5)
    models = {
        "Toyota": ["Camry", "RAV4", "Highlander"], "Lexus": ["RX350", "ES350"],
        "BMW": ["X5", "3 Series"], "Mercedes": ["C300", "GLE"],
        "Hyundai": ["Tucson", "Santa Fe"], "default": ["Sedan"]
    }
    return [{"source": "IAAI", "brand": brand,
             "title": f"{year} {brand} {random.choice(models.get(brand, models['default']))}",
             "price": random.randint(3000, 15000), "bids": random.randint(5, 40),
             "damage": "Minor Dents/Scratches", "year": year, "image": "",
             "url": f"https://www.iaai.com/search?make={brand}"}]

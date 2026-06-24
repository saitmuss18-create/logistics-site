import aiohttp
import json
import logging
from config import ANTHROPIC_API_KEY, BISHKEK_MARGIN, SHIPPING_COST_USD

logger = logging.getLogger(__name__)

async def analyze_cars(cars: list[dict]) -> list[dict]:
    """Анализирует список машин и отбирает самые выгодные для Бишкека"""
    
    # Считаем выгоду для каждой машины
    analyzed = []
    for car in cars:
        analyzed.append(calculate_profit(car))

    top_cars = analyzed[:10]
    
    # AI анализ через Claude
    if ANTHROPIC_API_KEY and top_cars:
        top_cars = await enrich_with_ai(top_cars)
    
    return top_cars


def calculate_profit(car: dict) -> dict:
    """Считает потенциальную прибыль при продаже в Бишкеке"""
    
    brand = car.get("brand", "default")
    margin = BISHKEK_MARGIN.get(brand, BISHKEK_MARGIN["default"])
    
    auction_price = car.get("price", 0)
    total_cost = auction_price + SHIPPING_COST_USD
    bishkek_price = total_cost * margin
    profit = bishkek_price - total_cost
    roi = (profit / total_cost * 100) if total_cost > 0 else 0
    
    car["total_cost_usd"] = round(total_cost)
    car["bishkek_price_usd"] = round(bishkek_price)
    car["profit_usd"] = round(profit)
    car["roi_percent"] = round(roi, 1)
    
    # Оценка спроса по количеству ставок
    bids = car.get("bids", 0)
    if bids >= 30:
        car["demand"] = "🔥 Очень высокий"
    elif bids >= 15:
        car["demand"] = "⚡ Высокий"
    elif bids >= 5:
        car["demand"] = "✅ Средний"
    else:
        car["demand"] = "❄️ Низкий"
    
    return car


async def enrich_with_ai(cars: list[dict]) -> list[dict]:
    """Добавляет AI-комментарий к каждой машине"""
    
    cars_summary = []
    for c in cars:
        cars_summary.append(
            f"{c['title']}, цена аукцион ${c['price']}, "
            f"доставка+покупка ${c['total_cost_usd']}, "
            f"ставки: {c['bids']}, повреждения: {c['damage']}"
        )
    
    prompt = f"""Ты эксперт по рынку автомобилей в Бишкеке, Кыргызстан. 
Оцени эти автомобили с аукционов США для перепродажи в Бишкеке.
Для каждого дай короткий комментарий (1-2 предложения) — почему выгодно или нет везти.
Учитывай спрос в Бишкеке, стоимость ремонта, популярность марки.

Машины:
{chr(10).join(f'{i+1}. {c}' for i, c in enumerate(cars_summary))}

Отвечай только JSON массивом с полем "comment" для каждой машины по порядку.
Пример: [{{"comment": "Текст"}}, {{"comment": "Текст"}}]"""

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=30
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    text = data["content"][0]["text"]
                    
                    # Чистим JSON
                    text = text.strip()
                    if text.startswith("```"):
                        text = text.split("```")[1]
                        if text.startswith("json"):
                            text = text[4:]
                    
                    comments = json.loads(text)
                    
                    for i, car in enumerate(cars):
                        if i < len(comments):
                            car["ai_comment"] = comments[i].get("comment", "")
                else:
                    logger.error(f"AI анализ: статус {resp.status}")
                    
    except Exception as e:
        logger.error(f"AI анализ ошибка: {e}")
        for car in cars:
            car.setdefault("ai_comment", "")
    
    return cars

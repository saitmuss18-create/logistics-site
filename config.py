import os

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL", "@CARS_USA_B2C")

# Anthropic (для AI-анализа)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Расписание (каждые N часов)
CHECK_INTERVAL_HOURS = 6

# Популярные марки в Бишкеке (спрос)
POPULAR_BRANDS = [
    "Toyota", "Lexus", "BMW", "Mercedes", "Hyundai",
    "Kia", "Honda", "Nissan", "Audi", "Chevrolet",
    "Ford", "Volkswagen", "Subaru", "Mitsubishi"
]

# Фильтры для поиска выгодных лотов
FILTERS = {
    "max_year_age": 10,        # не старше 10 лет
    "max_damage": ["Minor Dents/Scratches", "Normal Wear", "Hail", "Mechanical"],
    "min_bids": 5,             # минимум 5 ставок (значит машина востребована)
    "max_price_usd": 20000,    # максимальная цена лота
}

# Бишкекский рынок — примерные наценки при перепродаже
BISHKEK_MARGIN = {
    "Toyota": 1.4,
    "Lexus": 1.35,
    "BMW": 1.3,
    "Mercedes": 1.3,
    "Hyundai": 1.45,
    "Kia": 1.45,
    "Honda": 1.4,
    "default": 1.35
}

# Стоимость доставки США → Бишкек (примерно)
SHIPPING_COST_USD = 3500

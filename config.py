import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL", "-1004420009243")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "8874149160"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CHECK_INTERVAL_HOURS = 6

POPULAR_BRANDS = [
    "Toyota", "Lexus", "BMW", "Mercedes", "Hyundai",
    "Kia", "Honda", "Nissan", "Audi", "Chevrolet",
    "Ford", "Volkswagen", "Subaru", "Mitsubishi"
]

FILTERS = {
    "max_year_age": 10,
    "max_damage": ["Minor Dents/Scratches", "Normal Wear", "Hail", "Mechanical"],
    "min_bids": 5,
    "max_price_usd": 20000,
}

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

SHIPPING_COST_USD = 3500

# MFR AUTO — Auction Monitor Bot

Бот мониторит аукционы IAAI, Copart и bid.cars, анализирует выгодность машин для рынка Бишкека и публикует результаты в Telegram канал.

## Что делает бот

- 🔍 Парсит IAAI, Copart, bid.cars каждые 6 часов
- 📊 Анализирует спрос по количеству ставок
- 💰 Считает потенциальную прибыль (аукцион + доставка → продажа в Бишкеке)
- 🤖 AI-комментарий от Claude для каждой машины
- 📢 Публикует топ-5 выгодных лотов в Telegram канал

## Установка

```bash
# 1. Клонируй репозиторий
git clone https://github.com/saitmuss18-create/logistics-site.git
cd logistics-site

# 2. Установи зависимости
pip install -r requirements.txt

# 3. Настрой переменные окружения
cp .env.example .env
# Отредактируй .env — вставь свои токены

# 4. Запусти бота
python main.py
```

## Настройка (.env)

```
TELEGRAM_TOKEN=токен_от_BotFather
TELEGRAM_CHANNEL=@CARS_USA_B2C
ANTHROPIC_API_KEY=твой_ключ_anthropic (опционально)
```

## Структура проекта

```
├── main.py                    # Точка входа
├── config.py                  # Настройки и фильтры
├── scheduler.py               # Планировщик задач
├── scrapers/
│   ├── iaai_scraper.py        # Парсер IAAI
│   ├── copart_scraper.py      # Парсер Copart
│   └── bidcars_scraper.py     # Парсер bid.cars
├── analyzer/
│   └── market_analyzer.py     # Анализ рынка Бишкека + AI
└── publisher/
    └── telegram_publisher.py  # Публикация в Telegram
```

## Настройка фильтров (config.py)

- `CHECK_INTERVAL_HOURS` — как часто запускать (по умолчанию 6 часов)
- `POPULAR_BRANDS` — список марок для мониторинга
- `FILTERS` — максимальная цена, возраст, минимум ставок
- `SHIPPING_COST_USD` — стоимость доставки США → Бишкек
- `BISHKEK_MARGIN` — наценка при продаже по маркам

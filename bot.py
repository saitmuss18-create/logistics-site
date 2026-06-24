import os
import asyncio
import random
import json
import re
import time
import logging
from datetime import datetime
from dotenv import load_dotenv

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ua = UserAgent()

# Активные задачи поиска: chat_id -> task
active_searches: dict[int, asyncio.Task] = {}
# Найденные лоты (чтобы не дублировать)
found_lots: dict[int, set] = {}


# ───────────────────────────── HTTP helpers ──────────────────────────────────

def get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": ua.random,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
    })
    return s


async def slow_get(session: requests.Session, url: str, params: dict = None) -> requests.Response | None:
    """GET с случайной задержкой 20-90 секунд чтобы не словить блокировку."""
    delay = random.uniform(20, 90)
    logger.info(f"Waiting {delay:.1f}s before: {url}")
    await asyncio.sleep(delay)

    try:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp
    except Exception as e:
        logger.warning(f"Request failed {url}: {e}")
        # При ошибке ждём дольше
        await asyncio.sleep(random.uniform(60, 180))
        return None


# ───────────────────────────── Copart parser ─────────────────────────────────

async def search_copart(session: requests.Session, criteria: dict) -> list[dict]:
    """
    Copart имеет JSON API поиска. Используем его напрямую.
    Возвращает список лотов.
    """
    results = []

    make = criteria.get("make", "").upper()
    model = criteria.get("model", "").upper()
    year_from = criteria.get("year_from", "")
    year_to = criteria.get("year_to", "")
    price_from = criteria.get("price_from", "")
    price_to = criteria.get("price_to", "")

    # Строим поисковый запрос для Copart API
    search_text = f"{make} {model}".strip()
    if not search_text:
        return results

    url = "https://www.copart.com/public/lots/search-results"
    payload = {
        "query": [search_text],
        "filter": {
            "YEAR": {},
            "MAKE": {make: True} if make else {},
        },
        "sort": None,
        "page": 1,
        "size": 100,
        "watchListOnly": False,
        "searchCriteria": {
            "query": [search_text],
        },
    }

    if year_from or year_to:
        payload["filter"]["YEAR"] = {
            "from": year_from or "1990",
            "to": year_to or str(datetime.now().year),
        }

    # Сначала получаем главную страницу чтобы получить куки/csrf
    main_resp = await slow_get(session, "https://www.copart.com")
    if main_resp is None:
        return results

    session.headers.update({
        "User-Agent": ua.random,
        "Referer": "https://www.copart.com/",
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })

    await asyncio.sleep(random.uniform(15, 45))

    try:
        resp = session.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            lots = data.get("data", {}).get("results", {}).get("content", [])
            for lot in lots:
                year = lot.get("lcy", "")
                odometer = lot.get("orr", "")
                price = lot.get("ln", 0)

                # Фильтр по цене
                if price_from and price < int(price_from):
                    continue
                if price_to and price > int(price_to):
                    continue

                lot_number = str(lot.get("ln", ""))
                results.append({
                    "id": f"copart_{lot_number}",
                    "source": "Copart",
                    "title": f"{year} {lot.get('mkn', '')} {lot.get('mnn', '')}",
                    "year": year,
                    "make": lot.get("mkn", ""),
                    "model": lot.get("mnn", ""),
                    "odometer": f"{odometer} mi",
                    "price": f"${price:,}",
                    "damage": lot.get("dd", ""),
                    "url": f"https://www.copart.com/lot/{lot_number}",
                    "image": lot.get("tims", ""),
                })
        else:
            logger.warning(f"Copart returned {resp.status_code}")
    except Exception as e:
        logger.error(f"Copart parse error: {e}")

    return results


# ───────────────────────────── IAAI parser ───────────────────────────────────

async def search_iaai(session: requests.Session, criteria: dict) -> list[dict]:
    """IAAI поиск через веб-скрапинг."""
    results = []

    make = criteria.get("make", "")
    model = criteria.get("model", "")
    year_from = criteria.get("year_from", "")
    year_to = criteria.get("year_to", "")
    price_from = criteria.get("price_from", "")
    price_to = criteria.get("price_to", "")

    if not make:
        return results

    # Сначала открываем главную страницу
    main_resp = await slow_get(session, "https://www.iaai.com")
    if main_resp is None:
        return results

    session.headers.update({
        "User-Agent": ua.random,
        "Referer": "https://www.iaai.com/",
    })

    await asyncio.sleep(random.uniform(10, 30))

    # Параметры поиска IAAI
    params = {
        "Make": make,
        "Model": model,
        "StartYear": year_from,
        "EndYear": year_to,
        "RowsPerPage": "50",
        "CurrentPage": "1",
    }

    url = "https://www.iaai.com/Search"
    resp = await slow_get(session, url, params=params)
    if resp is None:
        return results

    try:
        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select("div.vehicle-card, div.search-card, li.result-item")

        if not cards:
            # Попробуем другой селектор — IAAI меняет вёрстку
            cards = soup.select("[data-vehicleid], [data-stocknumber]")

        for card in cards:
            try:
                title_el = card.select_one("h2, h3, .title, .vehicle-title")
                price_el = card.select_one(".bid, .current-bid, .price, [class*='bid']")
                link_el = card.select_one("a[href*='/VehicleDetails/']")

                title = title_el.get_text(strip=True) if title_el else ""
                price_raw = price_el.get_text(strip=True) if price_el else "0"
                price_num = int(re.sub(r"[^\d]", "", price_raw) or 0)
                href = link_el.get("href", "") if link_el else ""

                if not title:
                    continue

                # Фильтр по марке/модели (точное совпадение)
                if make.lower() not in title.lower():
                    continue
                if model and model.lower() not in title.lower():
                    continue

                # Фильтр по цене
                if price_from and price_num < int(price_from):
                    continue
                if price_to and price_num > int(price_to):
                    continue

                lot_id = re.search(r"(\d{7,})", href)
                lot_num = lot_id.group(1) if lot_id else str(hash(title))

                results.append({
                    "id": f"iaai_{lot_num}",
                    "source": "IAAI",
                    "title": title,
                    "price": f"${price_num:,}" if price_num else "N/A",
                    "url": f"https://www.iaai.com{href}" if href.startswith("/") else href,
                    "image": "",
                })
            except Exception as e:
                logger.debug(f"IAAI card parse error: {e}")
                continue

    except Exception as e:
        logger.error(f"IAAI parse error: {e}")

    return results


# ───────────────────────────── BidCars parser ────────────────────────────────

async def search_bidcars(session: requests.Session, criteria: dict) -> list[dict]:
    """BidCars.com — агрегатор Copart/IAAI с удобным API."""
    results = []

    make = criteria.get("make", "")
    model = criteria.get("model", "")
    year_from = criteria.get("year_from", "")
    year_to = criteria.get("year_to", "")
    price_from = criteria.get("price_from", "")
    price_to = criteria.get("price_to", "")

    if not make:
        return results

    main_resp = await slow_get(session, "https://bidcars.com")
    if main_resp is None:
        return results

    await asyncio.sleep(random.uniform(15, 40))

    session.headers.update({
        "User-Agent": ua.random,
        "Referer": "https://bidcars.com/",
    })

    # BidCars поиск
    params = {
        "make": make,
        "model": model,
        "year_from": year_from,
        "year_to": year_to,
        "bid_from": price_from,
        "bid_to": price_to,
        "per_page": "50",
    }
    params = {k: v for k, v in params.items() if v}

    url = "https://bidcars.com/auto/search"
    resp = await slow_get(session, url, params=params)
    if resp is None:
        return results

    try:
        soup = BeautifulSoup(resp.text, "lxml")

        # Ищем карточки лотов
        cards = soup.select(".lot-card, .car-item, article.card, .auction-item")
        if not cards:
            cards = soup.select("[class*='lot'], [class*='car-card'], [class*='vehicle']")

        for card in cards:
            try:
                title_el = card.select_one("h2, h3, .name, .title, [class*='title']")
                price_el = card.select_one(".price, .bid, [class*='price'], [class*='bid']")
                link_el = card.select_one("a[href]")
                img_el = card.select_one("img")

                title = title_el.get_text(strip=True) if title_el else ""
                price_raw = price_el.get_text(strip=True) if price_el else "0"
                price_num = int(re.sub(r"[^\d]", "", price_raw) or 0)
                href = link_el.get("href", "") if link_el else ""
                img = img_el.get("src", "") if img_el else ""

                if not title:
                    continue

                if make.lower() not in title.lower():
                    continue
                if model and model.lower() not in title.lower():
                    continue

                if price_from and price_num < int(price_from):
                    continue
                if price_to and price_num > int(price_to):
                    continue

                lot_id = re.search(r"(\d{6,})", href)
                lot_num = lot_id.group(1) if lot_id else str(hash(title + href))

                full_url = f"https://bidcars.com{href}" if href.startswith("/") else href

                results.append({
                    "id": f"bidcars_{lot_num}",
                    "source": "BidCars",
                    "title": title,
                    "price": f"${price_num:,}" if price_num else "N/A",
                    "url": full_url,
                    "image": img,
                })
            except Exception as e:
                logger.debug(f"BidCars card error: {e}")
                continue

    except Exception as e:
        logger.error(f"BidCars parse error: {e}")

    return results


# ───────────────────────────── Форматирование ────────────────────────────────

def format_lot(lot: dict) -> str:
    lines = [
        f"🚗 *{lot['title']}*",
        f"📍 Источник: {lot['source']}",
    ]
    if lot.get("year"):
        lines.append(f"📅 Год: {lot['year']}")
    if lot.get("odometer"):
        lines.append(f"🛣 Пробег: {lot['odometer']}")
    if lot.get("damage"):
        lines.append(f"💥 Повреждение: {lot['damage']}")
    lines.append(f"💰 Цена/ставка: {lot['price']}")
    lines.append(f"🔗 [Открыть лот]({lot['url']})")
    return "\n".join(lines)


def parse_criteria_text(text: str) -> dict:
    """
    Парсит свободный текст критериев.
    Пример: BMW 5 series 2018-2022 до 15000$
    """
    criteria = {}
    text_lower = text.lower()

    # Марки авто (расширенный список)
    makes = [
        "bmw", "mercedes", "audi", "toyota", "honda", "ford", "chevrolet",
        "lexus", "nissan", "hyundai", "kia", "volkswagen", "vw", "porsche",
        "land rover", "range rover", "jeep", "dodge", "ram", "volvo",
        "subaru", "mazda", "infiniti", "acura", "cadillac", "buick",
        "lincoln", "tesla", "genesis", "bentley", "lamborghini", "ferrari",
        "maserati", "alfa romeo", "fiat", "mini", "smart", "mitsubishi",
        "suzuki", "isuzu", "chrysler",
    ]
    for m in makes:
        if m in text_lower:
            criteria["make"] = m.upper().replace("VW", "VOLKSWAGEN")
            break

    # Годы: 2018-2022 или с 2018 по 2022 или 2020
    year_range = re.search(r"(\d{4})\s*[-–—]\s*(\d{4})", text)
    year_single = re.search(r"\b(19|20)\d{2}\b", text)
    if year_range:
        criteria["year_from"] = year_range.group(1)
        criteria["year_to"] = year_range.group(2)
    elif year_single:
        criteria["year_from"] = year_single.group(0)
        criteria["year_to"] = year_single.group(0)

    # Цена: до 15000, от 5000, 5000-15000$
    price_range = re.search(r"(\d[\d\s,]*)\s*[-–—]\s*(\d[\d\s,]*)\s*\$?", text)
    price_to = re.search(r"до\s+(\d[\d\s,]*)\s*\$?|under\s+\$?(\d[\d\s,]*)", text_lower)
    price_from = re.search(r"от\s+(\d[\d\s,]*)\s*\$?|from\s+\$?(\d[\d\s,]*)", text_lower)

    if price_range and int(re.sub(r"[\s,]", "", price_range.group(1))) > 1000:
        criteria["price_from"] = re.sub(r"[\s,]", "", price_range.group(1))
        criteria["price_to"] = re.sub(r"[\s,]", "", price_range.group(2))
    if price_to:
        val = price_to.group(1) or price_to.group(2)
        criteria["price_to"] = re.sub(r"[\s,]", "", val)
    if price_from:
        val = price_from.group(1) or price_from.group(2)
        criteria["price_from"] = re.sub(r"[\s,]", "", val)

    # Модель — берём слова после марки
    if "make" in criteria:
        make_pos = text_lower.find(criteria["make"].lower())
        after_make = text[make_pos + len(criteria["make"]):].strip()
        model_match = re.match(r"([a-zA-Zа-яёА-ЯЁ0-9\s\-]+?)(?:\d{4}|\$|до|от|под|за|$)", after_make)
        if model_match:
            model = model_match.group(1).strip()
            if model and len(model) > 1:
                criteria["model"] = model

    return criteria


# ───────────────────────────── Основной цикл поиска ─────────────────────────

async def search_loop(
    app: Application,
    chat_id: int,
    criteria: dict,
    duration_hours: float,
):
    """Запускает поиск на duration_hours часов, отправляя новые результаты в чат."""
    session = get_session()
    end_time = time.time() + duration_hours * 3600
    found_ids = found_lots.setdefault(chat_id, set())
    iteration = 0

    make = criteria.get("make", "?")
    model = criteria.get("model", "")
    label = f"{make} {model}".strip()

    await app.bot.send_message(
        chat_id,
        f"🔍 Начинаю поиск *{label}* на Copart, IAAI, BidCars\n"
        f"⏱ Буду искать до *{duration_hours} ч* медленно и осторожно\n"
        f"Первые результаты придут через 2-5 минут...",
        parse_mode="Markdown",
    )

    while time.time() < end_time:
        iteration += 1
        logger.info(f"Search iteration {iteration} for chat {chat_id}")

        # Перемешиваем порядок сайтов каждый раз
        searchers = [search_copart, search_iaai, search_bidcars]
        random.shuffle(searchers)

        new_count = 0
        for searcher in searchers:
            if time.time() >= end_time:
                break
            try:
                results = await searcher(session, criteria)
                for lot in results:
                    if lot["id"] not in found_ids:
                        found_ids.add(lot["id"])
                        new_count += 1
                        msg = format_lot(lot)
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔗 Открыть лот", url=lot["url"])]
                        ])
                        await app.bot.send_message(
                            chat_id,
                            msg,
                            parse_mode="Markdown",
                            reply_markup=keyboard,
                            disable_web_page_preview=False,
                        )
                        await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Searcher error: {e}")

            # Пауза между сайтами
            await asyncio.sleep(random.uniform(30, 90))

        # Пауза между итерациями (5-15 минут)
        pause = random.uniform(300, 900)
        remaining = end_time - time.time()
        if remaining <= 0:
            break

        next_in = min(pause, remaining)
        logger.info(f"Iteration {iteration} done. New: {new_count}. Next in {next_in:.0f}s")

        await app.bot.send_message(
            chat_id,
            f"✅ Итерация {iteration}: найдено *{new_count}* новых лотов\n"
            f"⏳ Следующая проверка через {next_in/60:.0f} мин\n"
            f"🕐 Осталось: {remaining/3600:.1f} ч",
            parse_mode="Markdown",
        )

        # Меняем сессию (новый User-Agent, куки)
        session = get_session()
        await asyncio.sleep(next_in)

    total = len(found_ids)
    await app.bot.send_message(
        chat_id,
        f"🏁 Поиск завершён!\n"
        f"📊 Всего найдено уникальных лотов: *{total}*\n"
        f"Используйте /search чтобы начать новый поиск.",
        parse_mode="Markdown",
    )
    active_searches.pop(chat_id, None)


# ───────────────────────────── Telegram handlers ─────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Бот поиска аукционных авто*\n\n"
        "Ищу реальные лоты на Copart, IAAI, BidCars\n\n"
        "📌 *Команды:*\n"
        "/search — начать поиск\n"
        "/stop — остановить поиск\n"
        "/status — статус текущего поиска\n\n"
        "💡 *Пример:*\n"
        "`/search BMW 5 2018-2022 до 12000`\n"
        "`/search Toyota Camry от 5000 до 15000`\n"
        "`/search Mercedes E класс 2019`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id in active_searches:
        await update.message.reply_text(
            "⚠️ Поиск уже запущен! Используйте /stop чтобы остановить."
        )
        return

    query = " ".join(context.args)
    if not query:
        await update.message.reply_text(
            "❌ Укажите критерии поиска.\n\n"
            "Пример: `/search BMW 5 series 2018-2022 до 15000`",
            parse_mode="Markdown",
        )
        return

    criteria = parse_criteria_text(query)
    if not criteria.get("make"):
        await update.message.reply_text(
            "❌ Не могу определить марку автомобиля.\n"
            "Укажите марку явно, например: *BMW*, *Toyota*, *Mercedes*",
            parse_mode="Markdown",
        )
        return

    # Спрашиваем сколько часов искать
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1 час", callback_data=f"duration:1:{query}"),
            InlineKeyboardButton("2 часа", callback_data=f"duration:2:{query}"),
            InlineKeyboardButton("3 часа", callback_data=f"duration:3:{query}"),
        ]
    ])

    summary_lines = [f"✅ *Критерии поиска:*\n🚗 Марка: {criteria.get('make', '—')}"]
    if criteria.get("model"):
        summary_lines.append(f"📋 Модель: {criteria['model']}")
    if criteria.get("year_from"):
        yr = criteria["year_from"]
        if criteria.get("year_to") and criteria["year_to"] != yr:
            yr += f"–{criteria['year_to']}"
        summary_lines.append(f"📅 Год: {yr}")
    if criteria.get("price_from") or criteria.get("price_to"):
        p = ""
        if criteria.get("price_from"):
            p += f"от ${criteria['price_from']} "
        if criteria.get("price_to"):
            p += f"до ${criteria['price_to']}"
        summary_lines.append(f"💰 Цена: {p.strip()}")

    summary_lines.append("\n⏱ *Как долго искать?*")
    await update.message.reply_text(
        "\n".join(summary_lines),
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def cb_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":", 2)
    hours = float(parts[1])
    search_query = parts[2]

    chat_id = update.effective_chat.id
    criteria = parse_criteria_text(search_query)

    # Сбрасываем найденные лоты для нового поиска
    found_lots[chat_id] = set()

    task = asyncio.create_task(
        search_loop(context.application, chat_id, criteria, hours)
    )
    active_searches[chat_id] = task

    await query.edit_message_text(
        f"🚀 Запускаю поиск на {hours:.0f} ч...",
        parse_mode="Markdown",
    )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    task = active_searches.pop(chat_id, None)
    if task:
        task.cancel()
        await update.message.reply_text("⛔ Поиск остановлен.")
    else:
        await update.message.reply_text("Нет активного поиска.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in active_searches:
        found = len(found_lots.get(chat_id, set()))
        await update.message.reply_text(
            f"🔍 Поиск активен\n📊 Найдено лотов: *{found}*",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("Поиск не запущен. Используйте /search")


# ───────────────────────────── Main ─────────────────────────────────────────

def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в .env файле")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CallbackQueryHandler(cb_duration, pattern=r"^duration:"))

    logger.info("Bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

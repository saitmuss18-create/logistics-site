import asyncio
import aiohttp
import json
import logging
import os
from pathlib import Path
from config import TELEGRAM_TOKEN, ADMIN_CHAT_ID

logger = logging.getLogger(__name__)

SETTINGS_FILE = Path("settings.json")

ALL_BRANDS = [
    "Toyota", "Lexus", "BMW", "Mercedes", "Hyundai",
    "Kia", "Honda", "Nissan", "Audi", "Chevrolet",
    "Ford", "Volkswagen", "Subaru", "Mitsubishi"
]

ALL_MODELS = {
    "Toyota": ["Camry", "RAV4", "Highlander", "Venza", "Land Cruiser", "Prius", "Corolla", "Sienna"],
    "Lexus": ["RX 350", "NX 300", "ES 350", "GX 460", "LX 570", "UX 200"],
    "BMW": ["X3", "X5", "X7", "3 Series", "5 Series", "7 Series", "M3", "M5"],
    "Mercedes": ["E-Class", "C-Class", "GLC 300", "GLE 350", "S-Class", "G-Class"],
    "Hyundai": ["Tucson", "Santa Fe", "Palisade", "Sonata", "Elantra"],
    "Kia": ["Sportage", "Sorento", "Telluride", "K5", "Carnival"],
    "Honda": ["CR-V", "Pilot", "Accord", "Civic", "Odyssey"],
    "Nissan": ["Rogue", "Pathfinder", "Murano", "Altima", "Titan"],
    "Audi": ["Q5", "Q7", "A4", "A6", "e-tron"],
    "Chevrolet": ["Tahoe", "Suburban", "Traverse", "Equinox", "Silverado"],
    "Ford": ["Explorer", "F-150", "Escape", "Edge", "Expedition"],
    "Volkswagen": ["Tiguan", "Atlas", "Passat", "Jetta"],
    "Subaru": ["Outback", "Forester", "Crosstrek", "Ascent"],
    "Mitsubishi": ["Outlander", "Eclipse Cross", "Galant"],
}

_waiting_for = {}


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {
        "max_year_age": 10, "max_price_usd": 20000, "min_bids": 5,
        "brands": ALL_BRANDS[:5], "models": [], "check_interval_hours": 6
    }


def save_settings(s: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def get_api():
    token = os.getenv('TELEGRAM_TOKEN') or TELEGRAM_TOKEN
    return f"https://api.telegram.org/bot{token}"


async def send(session, chat_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if keyboard:
        payload["reply_markup"] = json.dumps({"inline_keyboard": keyboard})
    async with session.post(f"{get_api()}/sendMessage", json=payload) as r:
        return await r.json()


async def edit(session, chat_id, msg_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "message_id": msg_id, "text": text, "parse_mode": "Markdown"}
    if keyboard:
        payload["reply_markup"] = json.dumps({"inline_keyboard": keyboard})
    async with session.post(f"{get_api()}/editMessageText", json=payload):
        pass


async def answer_callback(session, callback_id):
    async with session.post(f"{get_api()}/answerCallbackQuery",
                            json={"callback_query_id": callback_id}):
        pass


def main_menu_keyboard():
    return [
        [{"text": "⚙️ Фильтры", "callback_data": "menu_filters"}],
        [{"text": "🚀 Запустить сейчас", "callback_data": "menu_run"}],
        [{"text": "📊 Текущие настройки", "callback_data": "menu_status"}],
    ]


def filters_keyboard():
    s = load_settings()
    model_count = len(s.get("models", []))
    model_label = f"✅ {model_count} выбрано" if model_count else "Все модели"
    return [
        [{"text": f"📅 Возраст: не старше {s['max_year_age']} лет", "callback_data": "set_year_age"}],
        [{"text": f"💰 Макс. цена: ${s['max_price_usd']:,}", "callback_data": "set_price"}],
        [{"text": f"🔨 Мин. ставок: {s['min_bids']}", "callback_data": "set_bids"}],
        [{"text": f"⏰ Интервал: {s['check_interval_hours']} ч", "callback_data": "set_interval"}],
        [{"text": "🚗 Марки авто", "callback_data": "set_brands"}],
        [{"text": f"🔍 Модели: {model_label}", "callback_data": "set_models_brands"}],
        [{"text": "◀️ Назад", "callback_data": "menu_back"}],
    ]


def brands_keyboard():
    s = load_settings()
    selected = s.get("brands", [])
    rows = []
    for i in range(0, len(ALL_BRANDS), 2):
        row = []
        for brand in ALL_BRANDS[i:i+2]:
            mark = "✅" if brand in selected else "☐"
            row.append({"text": f"{mark} {brand}", "callback_data": f"brand_{brand}"})
        rows.append(row)
    rows.append([{"text": "◀️ Назад", "callback_data": "menu_filters"}])
    return rows


def models_brands_keyboard():
    s = load_settings()
    selected_brands = s.get("brands", ALL_BRANDS[:5])
    rows = []
    for brand in selected_brands:
        rows.append([{"text": f"🚗 {brand}", "callback_data": f"models_for_{brand}"}])
    rows.append([{"text": "🗑 Сбросить все модели", "callback_data": "models_reset"}])
    rows.append([{"text": "◀️ Назад", "callback_data": "menu_filters"}])
    return rows


def models_keyboard(brand: str):
    s = load_settings()
    selected = s.get("models", [])
    models = ALL_MODELS.get(brand, [])
    rows = []
    for i in range(0, len(models), 2):
        row = []
        for model in models[i:i+2]:
            key = f"{brand}:{model}"
            mark = "✅" if key in selected else "☐"
            row.append({"text": f"{mark} {model}", "callback_data": f"model_{brand}_{model}"})
        rows.append(row)
    rows.append([{"text": "◀️ Назад к маркам", "callback_data": "set_models_brands"}])
    return rows


def status_text():
    s = load_settings()
    from datetime import datetime
    min_year = datetime.now().year - s['max_year_age']
    brands = ", ".join(s.get("brands", []))
    models = s.get("models", [])
    model_text = "\n".join(f"  • {m.split(':')[1]}" for m in models) if models else "  Все модели"
    return (
        f"📊 *Текущие настройки:*\n\n"
        f"📅 Год: от {min_year} (не старше {s['max_year_age']} лет)\n"
        f"💰 Макс. цена: ${s['max_price_usd']:,}\n"
        f"🔨 Мин. ставок: {s['min_bids']}\n"
        f"⏰ Интервал: {s['check_interval_hours']} ч\n"
        f"🚗 Марки: {brands}\n"
        f"🔍 Модели:\n{model_text}"
    )


async def handle_message(session, msg):
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "")

    if chat_id != ADMIN_CHAT_ID:
        return

    state = _waiting_for.get(chat_id)

    if state:
        s = load_settings()
        try:
            if state == "year_age":
                val = int(text)
                if 1 <= val <= 20:
                    s["max_year_age"] = val
                    save_settings(s)
                    await send(session, chat_id, f"✅ Возраст: не старше *{val} лет*")
                else:
                    await send(session, chat_id, "❌ Введи число от 1 до 20")
            elif state == "price":
                val = int(text.replace(",", "").replace("$", ""))
                if 1000 <= val <= 100000:
                    s["max_price_usd"] = val
                    save_settings(s)
                    await send(session, chat_id, f"✅ Макс. цена: *${val:,}*")
                else:
                    await send(session, chat_id, "❌ Введи сумму от $1,000 до $100,000")
            elif state == "bids":
                val = int(text)
                if 0 <= val <= 100:
                    s["min_bids"] = val
                    save_settings(s)
                    await send(session, chat_id, f"✅ Мин. ставок: *{val}*")
                else:
                    await send(session, chat_id, "❌ Введи число от 0 до 100")
            elif state == "interval":
                val = int(text)
                if 1 <= val <= 24:
                    s["check_interval_hours"] = val
                    save_settings(s)
                    await send(session, chat_id, f"✅ Интервал: *{val} ч*")
                else:
                    await send(session, chat_id, "❌ Введи число от 1 до 24")
        except ValueError:
            await send(session, chat_id, "❌ Введи число")

        _waiting_for.pop(chat_id, None)
        await send(session, chat_id, "Главное меню:", main_menu_keyboard())
        return

    if text in ("/start", "/menu"):
        await send(session, chat_id, "👋 *MFR AUTO Admin Panel*\n\nВыбери действие:", main_menu_keyboard())


async def handle_callback(session, cb):
    chat_id = cb["message"]["chat"]["id"]
    msg_id = cb["message"]["message_id"]
    data = cb["data"]

    if chat_id != ADMIN_CHAT_ID:
        return

    await answer_callback(session, cb["id"])

    if data == "menu_back":
        await edit(session, chat_id, msg_id, "👋 *MFR AUTO Admin Panel*\n\nВыбери действие:", main_menu_keyboard())

    elif data == "menu_filters":
        await edit(session, chat_id, msg_id, "⚙️ *Фильтры поиска:*", filters_keyboard())

    elif data == "menu_status":
        await edit(session, chat_id, msg_id, status_text(), [[{"text": "◀️ Назад", "callback_data": "menu_back"}]])

    elif data == "menu_run":
        await edit(session, chat_id, msg_id, "🚀 Запускаю поиск...", None)
        from scheduler import run_once
        asyncio.create_task(run_once())

    elif data == "set_year_age":
        _waiting_for[chat_id] = "year_age"
        await send(session, chat_id, "📅 Введи макс. возраст авто в годах (например: *10*)")

    elif data == "set_price":
        _waiting_for[chat_id] = "price"
        await send(session, chat_id, "💰 Введи максимальную цену в $ (например: *20000*)")

    elif data == "set_bids":
        _waiting_for[chat_id] = "bids"
        await send(session, chat_id, "🔨 Введи минимальное кол-во ставок (например: *5*)")

    elif data == "set_interval":
        _waiting_for[chat_id] = "interval"
        await send(session, chat_id, "⏰ Введи интервал проверки в часах (например: *6*)")

    elif data == "set_brands":
        await edit(session, chat_id, msg_id, "🚗 *Выбери марки авто:*", brands_keyboard())

    elif data.startswith("brand_"):
        brand = data[6:]
        s = load_settings()
        brands = s.get("brands", [])
        if brand in brands:
            brands.remove(brand)
            s["models"] = [m for m in s.get("models", []) if not m.startswith(f"{brand}:")]
        else:
            brands.append(brand)
        s["brands"] = brands
        save_settings(s)
        await edit(session, chat_id, msg_id, "🚗 *Выбери марки авто:*", brands_keyboard())

    elif data == "set_models_brands":
        await edit(session, chat_id, msg_id, "🔍 *Выбери марку для настройки моделей:*", models_brands_keyboard())

    elif data.startswith("models_for_"):
        brand = data[11:]
        await edit(session, chat_id, msg_id, f"🔍 *Модели {brand}:*\n_(пусто = все модели)_", models_keyboard(brand))

    elif data.startswith("model_"):
        parts = data[6:].split("_", 1)
        if len(parts) == 2:
            brand, model = parts[0], parts[1]
            key = f"{brand}:{model}"
            s = load_settings()
            models = s.get("models", [])
            if key in models:
                models.remove(key)
            else:
                models.append(key)
            s["models"] = models
            save_settings(s)
            await edit(session, chat_id, msg_id, f"🔍 *Модели {brand}:*", models_keyboard(brand))

    elif data == "models_reset":
        s = load_settings()
        s["models"] = []
        save_settings(s)
        await edit(session, chat_id, msg_id, "✅ Модели сброшены — ищем все модели", filters_keyboard())


async def run_admin_bot():
    logger.info("🎛 Админ-бот запущен")
    offset = 0
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(
                    f"{get_api()}/getUpdates",
                    params={"offset": offset, "timeout": 30},
                    timeout=aiohttp.ClientTimeout(total=35)
                ) as resp:
                    data = await resp.json()
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        if "message" in update:
                            await handle_message(session, update["message"])
                        elif "callback_query" in update:
                            await handle_callback(session, update["callback_query"])
            except Exception as e:
                logger.error(f"Админ-бот ошибка: {e}")
                await asyncio.sleep(5)

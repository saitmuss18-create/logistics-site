"""
Менеджер куки для сайтов с защитой.
Открывает Chrome один раз, сохраняет куки в файл.
Дальше все запросы идут через aiohttp с сохранёнными куки — Chrome не нужен.
"""
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

COOKIES_DIR = Path("cookies")
COOKIES_DIR.mkdir(exist_ok=True)

SITES = {
    "copart": {
        "url": "https://www.copart.com/",
        "file": COOKIES_DIR / "copart.json",
        "wait": 20,
        "check_url": "https://api.copart.com/v2/public/lots/search",
    },
    "iaai": {
        "url": "https://www.iaai.com/Search",
        "file": COOKIES_DIR / "iaai.json",
        "wait": 20,
        "check_url": "https://www.iaai.com/Search",
    },
}


def save_cookies(site: str) -> bool:
    """
    Открывает Chrome, загружает сайт, ждёт пока пользователь пройдёт капчу/авторизацию,
    сохраняет куки в файл. Возвращает True если успешно.
    """
    cfg = SITES.get(site)
    if not cfg:
        logger.error(f"Неизвестный сайт: {site}")
        return False

    try:
        from scrapers.bidcars_scraper import get_driver
        driver = get_driver()
        try:
            logger.info(f"Открываю {cfg['url']} для получения куки...")
            driver.get(cfg["url"])

            # Даём пользователю время пройти капчу если нужно
            wait = cfg["wait"]
            logger.info(f"Жду {wait} сек (пользователь может взаимодействовать с браузером)...")
            time.sleep(wait)

            # Сохраняем куки
            cookies = driver.get_cookies()
            cookie_data = {
                "site": site,
                "url": cfg["url"],
                "saved_at": datetime.now().isoformat(),
                "cookies": cookies,
            }
            cfg["file"].write_text(
                json.dumps(cookie_data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            logger.info(f"Сохранено {len(cookies)} куки для {site}")
            return True

        finally:
            driver.quit()

    except Exception as e:
        logger.error(f"save_cookies {site}: {e}")
        return False


def load_cookies(site: str) -> dict | None:
    """
    Загружает куки из файла. Возвращает dict {name: value} или None если нет/устарели.
    """
    cfg = SITES.get(site)
    if not cfg or not cfg["file"].exists():
        return None

    try:
        data = json.loads(cfg["file"].read_text(encoding="utf-8"))
        saved_at = datetime.fromisoformat(data["saved_at"])

        # Куки старше 7 дней — считаем устаревшими
        if datetime.now() - saved_at > timedelta(days=7):
            logger.warning(f"Куки {site} устарели ({saved_at.strftime('%d.%m.%Y')})")
            return None

        cookies = {c["name"]: c["value"] for c in data.get("cookies", [])}
        logger.info(f"Загружено {len(cookies)} куки для {site} (от {saved_at.strftime('%d.%m %H:%M')})")
        return cookies

    except Exception as e:
        logger.error(f"load_cookies {site}: {e}")
        return None


def cookies_age(site: str) -> str:
    """Возвращает строку с возрастом куки для отображения в боте."""
    cfg = SITES.get(site)
    if not cfg or not cfg["file"].exists():
        return "❌ нет"

    try:
        data = json.loads(cfg["file"].read_text(encoding="utf-8"))
        saved_at = datetime.fromisoformat(data["saved_at"])
        age = datetime.now() - saved_at
        days = age.days
        hours = age.seconds // 3600

        if days > 7:
            return f"⚠️ устарели ({days} дн.)"
        elif days > 0:
            return f"✅ {days} дн. назад"
        else:
            return f"✅ {hours} ч. назад"
    except Exception:
        return "❓ неизвестно"

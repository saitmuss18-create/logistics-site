"""
Запусти: python test_bidcars.py
Откроет bid.cars, сохранит скриншот screenshot.png и выведет найденные данные.
"""
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

options = Options()
# options.add_argument("--headless")  # Пока без headless — видим браузер
options.add_argument("--window-size=1920,1080")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

print("Открываю bid.cars...")
driver.get("https://bid.cars/en/search?make=toyota&sort=bids&order=desc")
time.sleep(5)

print(f"Заголовок страницы: {driver.title}")
print(f"URL: {driver.current_url}")

# Скриншот
driver.save_screenshot("screenshot.png")
print("Скриншот сохранён: screenshot.png")

# Ищем все ссылки на лоты
lot_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/lot/'], a[href*='/en/lot']")
print(f"\nНайдено ссылок на лоты: {len(lot_links)}")
for a in lot_links[:5]:
    print(f"  Ссылка: {a.get_attribute('href')}")

# Ищем все картинки
images = driver.find_elements(By.TAG_NAME, "img")
print(f"\nНайдено изображений: {len(images)}")
for img in images[:10]:
    src = img.get_attribute("src") or img.get_attribute("data-src") or ""
    if src and "http" in src and not src.endswith(".svg"):
        print(f"  Фото: {src[:100]}")

# Все классы элементов (для анализа структуры)
all_els = driver.find_elements(By.CSS_SELECTOR, "[class]")
classes = set()
for el in all_els[:200]:
    cls = el.get_attribute("class") or ""
    for c in cls.split():
        if any(w in c.lower() for w in ["lot", "card", "vehicle", "car", "item"]):
            classes.add(cls[:80])
print(f"\nКлассы карточек найдены:")
for c in list(classes)[:15]:
    print(f"  {c}")

input("\nНажми Enter чтобы закрыть браузер...")
driver.quit()

"""
Запусти: python test_bidcars.py
"""
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

options = Options()
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

print("Жду 10 секунд...")
time.sleep(10)

# Прокручиваем страницу вниз
driver.execute_script("window.scrollTo(0, 500)")
time.sleep(3)
driver.execute_script("window.scrollTo(0, 1500)")
time.sleep(3)

print(f"Заголовок: {driver.title}")
print(f"URL: {driver.current_url}")

driver.save_screenshot("screenshot.png")
print("Скриншот сохранён: screenshot.png — ОТКРОЙ ЕГО И ПОСМОТРИ")

# Все ссылки на странице
all_links = driver.find_elements(By.TAG_NAME, "a")
print(f"\nВсего ссылок: {len(all_links)}")
lot_links = [a for a in all_links if "/lot" in (a.get_attribute("href") or "")]
print(f"Ссылок с /lot: {len(lot_links)}")
for a in lot_links[:5]:
    print(f"  {a.get_attribute('href')}")

# Все картинки
images = driver.find_elements(By.TAG_NAME, "img")
car_imgs = [i for i in images if any(x in (i.get_attribute("src") or "") for x in ["copart", "iaai", "bid.cars", "cdn", "upload", "photo", "car", "vehicle", "lot", "image"])]
print(f"\nФото авто: {len(car_imgs)}")
for img in car_imgs[:5]:
    print(f"  {img.get_attribute('src')[:120]}")

# Весь текст страницы (первые 2000 символов)
body_text = driver.find_element(By.TAG_NAME, "body").text
print(f"\nТекст страницы (первые 1000 символов):")
print(body_text[:1000])

input("\nНажми Enter чтобы закрыть...")
driver.quit()

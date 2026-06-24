"""
Запусти: python test_bidcars.py
Бот заходит в каждый лот, читает фото и данные, потом следующий.
"""
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

print("Открываю bid.cars...")
options = uc.ChromeOptions()
options.add_argument("--window-size=1920,1080")
driver = uc.Chrome(options=options, version_main=149)

def js_click(el):
    driver.execute_script("arguments[0].click();", el)

# === ШАГ 1: Поиск Toyota ===
driver.get("https://bid.cars/en/search")
time.sleep(5)

# Type
type_btn = WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.CSS_SELECTOR, ".search_make_transport .dropdown-toggle"))
)
js_click(type_btn); time.sleep(1)
js_click(driver.find_element(By.XPATH, "//a[contains(@class,'dropdown-item') and contains(text(),'Automobile')]"))
time.sleep(2)

# Make
js_click(WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.CSS_SELECTOR, ".search_make_filter .dropdown-toggle"))
))
time.sleep(1)
js_click(driver.find_element(By.XPATH, "//a[contains(@class,'dropdown-item') and text()='Toyota']"))
time.sleep(2)

# Search
js_click(WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-primary[type='submit']"))
))
time.sleep(8)
print(f"URL результатов: {driver.current_url}")

# Скроллим для загрузки карточек
for pos in range(0, 4000, 600):
    driver.execute_script(f"window.scrollTo(0, {pos});")
    time.sleep(0.2)
time.sleep(1)

# Собираем ссылки на лоты
anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/lot/']")
seen = set()
lot_urls = []
for a in anchors:
    href = a.get_attribute("href") or ""
    if href and href not in seen and "#" not in href:
        seen.add(href)
        lot_urls.append(href)

print(f"\nНайдено лотов: {len(lot_urls)}")
print("Захожу в каждый лот...\n")

# === ШАГ 2: Заходим в каждый лот ===
results = []
for i, url in enumerate(lot_urls[:5], 1):
    print(f"[{i}/5] {url}")
    driver.get(url)
    time.sleep(4)

    # Скроллим для загрузки фото
    for pos in range(0, 2000, 400):
        driver.execute_script(f"window.scrollTo(0, {pos});")
        time.sleep(0.2)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)

    # Заголовок
    title = ""
    for sel in ["h1", ".lot-title", "[class*='vehicle-title']"]:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if el.text.strip():
                title = el.text.strip()
                break
        except Exception:
            pass

    # Все фото на странице лота
    images = []
    for img in driver.find_elements(By.TAG_NAME, "img"):
        for attr in ["src", "data-src", "data-lazy", "data-original"]:
            src = img.get_attribute(attr) or ""
            if (src and src.startswith("http") and ".svg" not in src
                    and "logo" not in src and "icon" not in src
                    and "placeholder" not in src and "flag" not in src):
                if src not in images:
                    images.append(src)
                break

    # Текст страницы (цена, год, повреждения)
    body_text = driver.find_element(By.TAG_NAME, "body").text
    price_line = next((l for l in body_text.split("\n") if "$" in l and any(c.isdigit() for c in l)), "")

    print(f"  Заголовок: {title}")
    print(f"  Цена: {price_line.strip()[:60]}")
    print(f"  Фото ({len(images)}): {images[0][:100] if images else '❌ нет'}")
    if len(images) > 1:
        print(f"            {images[1][:100]}")

    driver.save_screenshot(f"lot_{i}.png")
    results.append({"url": url, "title": title, "images": images[:3]})
    print()

print(f"\n✅ Готово! Обработано {len(results)} лотов")
print("Скриншоты: lot_1.png ... lot_5.png")

input("\nНажми Enter чтобы закрыть...")
driver.quit()

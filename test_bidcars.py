"""
Запусти: python test_bidcars.py
"""
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

print("Открываю bid.cars через undetected-chromedriver...")
options = uc.ChromeOptions()
options.add_argument("--window-size=1920,1080")

driver = uc.Chrome(options=options, version_main=149)

def js_click(el):
    driver.execute_script("arguments[0].click();", el)

driver.get("https://bid.cars/en/search")
time.sleep(5)

print(f"Заголовок: {driver.title}")
driver.save_screenshot("step1_loaded.png")

# Шаг 1: Type = Automobile
print("\nШаг 1: Выбираем тип Automobile...")
try:
    type_btn = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".search_make_transport .dropdown-toggle"))
    )
    js_click(type_btn)
    time.sleep(1)
    automobile = driver.find_element(By.XPATH, "//a[contains(@class,'dropdown-item') and contains(text(),'Automobile')]")
    js_click(automobile)
    time.sleep(2)
    print("  ✅ Тип выбран!")
except Exception as e:
    print(f"  ❌ Ошибка: {e}")

# Шаг 2: Make = Toyota
print("\nШаг 2: Выбираем марку Toyota...")
try:
    make_btn = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".search_make_filter .dropdown-toggle"))
    )
    js_click(make_btn)
    time.sleep(1)
    toyota = driver.find_element(By.XPATH, "//a[contains(@class,'dropdown-item') and text()='Toyota']")
    js_click(toyota)
    time.sleep(2)
    print("  ✅ Марка выбрана!")
except Exception as e:
    print(f"  ❌ Ошибка: {e}")

# Шаг 3: Search
print("\nШаг 3: Нажимаем Search...")
try:
    search_btn = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-primary[type='submit']"))
    )
    js_click(search_btn)
    time.sleep(8)
    print(f"  URL: {driver.current_url}")
except Exception as e:
    print(f"  ❌ Ошибка: {e}")

driver.save_screenshot("step4_results.png")
print("Скриншот step4_results.png")

# Ждём лоты
try:
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/lot/']"))
    )
except Exception:
    time.sleep(3)

# Собираем ссылки на лоты
lot_anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/lot/']")
seen = set()
lot_data = []
for a in lot_anchors:
    href = a.get_attribute("href") or ""
    if href and href not in seen and "#" not in href:
        seen.add(href)
        # Фото внутри ссылки
        imgs = a.find_elements(By.TAG_NAME, "img")
        img_url = ""
        for img in imgs:
            src = img.get_attribute("src") or img.get_attribute("data-src") or ""
            if src and src.startswith("http") and ".svg" not in src and "placeholder" not in src:
                img_url = src
                break
        text = a.text.strip()[:100]
        lot_data.append((href, img_url, text))

print(f"\nНайдено лотов: {len(lot_data)}")
for url, img, txt in lot_data[:8]:
    print(f"\n  URL: {url}")
    print(f"  Фото: {img[:100] if img else '❌ нет фото'}")
    print(f"  Текст: {txt[:80]}")

input("\nНажми Enter чтобы закрыть...")
driver.quit()

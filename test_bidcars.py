"""
Тест: заходим в 1 лот Toyota и собираем ВСЕ фото
Запусти: python test_bidcars.py
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

# Поиск Toyota
driver.get("https://bid.cars/en/search")
time.sleep(5)

js_click(WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.CSS_SELECTOR, ".search_make_transport .dropdown-toggle"))
))
time.sleep(1)
js_click(driver.find_element(By.XPATH, "//a[contains(@class,'dropdown-item') and contains(text(),'Automobile')]"))
time.sleep(2)

js_click(WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.CSS_SELECTOR, ".search_make_filter .dropdown-toggle"))
))
time.sleep(1)
js_click(driver.find_element(By.XPATH, "//a[contains(@class,'dropdown-item') and text()='Toyota']"))
time.sleep(2)

js_click(WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-primary[type='submit']"))
))
time.sleep(8)

# Берём первую ссылку на лот
anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/lot/']")
seen = set()
lot_urls = []
for a in anchors:
    href = a.get_attribute("href") or ""
    if href and href not in seen and "#" not in href:
        seen.add(href)
        lot_urls.append(href)

print(f"Найдено лотов: {len(lot_urls)}")

# Заходим в первый лот
lot_url = lot_urls[0]
print(f"\nЗахожу в лот: {lot_url}")
driver.get(lot_url)
time.sleep(5)

# Скроллим чтобы всё загрузилось
for pos in range(0, 3000, 300):
    driver.execute_script(f"window.scrollTo(0, {pos});")
    time.sleep(0.15)
driver.execute_script("window.scrollTo(0, 0);")
time.sleep(2)

driver.save_screenshot("lot_page.png")
print("Скриншот lot_page.png")

# Заголовок
title = ""
for sel in ["h1", ".lot-title", "[class*='title']"]:
    try:
        el = driver.find_element(By.CSS_SELECTOR, sel)
        if el.text.strip():
            title = el.text.strip()
            break
    except Exception:
        pass
print(f"Заголовок: {title}")

# Выводим HTML всех img для анализа
print("\n--- ВСЕ img на странице лота ---")
all_imgs = driver.find_elements(By.TAG_NAME, "img")
print(f"Всего img: {len(all_imgs)}")
for i, img in enumerate(all_imgs):
    src = img.get_attribute("src") or ""
    dsrc = img.get_attribute("data-src") or ""
    cls = img.get_attribute("class") or ""
    alt = img.get_attribute("alt") or ""
    if src or dsrc:
        print(f"  [{i}] src={src[:90]}")
        if dsrc:
            print(f"       data-src={dsrc[:90]}")
        print(f"       class={cls[:50]} alt={alt[:30]}")

# Ищем фото галереи
print("\n--- Фото авто (фильтрованные) ---")
car_photos = []
skip_words = ["logo", "icon", "flag", "placeholder", "facebook", "instagram", "twitter", "avatar", "user", "banner"]
for img in all_imgs:
    for attr in ["src", "data-src", "data-lazy", "data-original"]:
        src = img.get_attribute(attr) or ""
        if src and src.startswith("http") and ".svg" not in src:
            if not any(w in src.lower() for w in skip_words):
                if src not in car_photos:
                    car_photos.append(src)
        if src:
            break

print(f"Фото авто: {len(car_photos)}")
for p in car_photos:
    print(f"  {p}")

# Также проверяем через JS — вдруг фото в JS-переменных
print("\n--- Ищем фото через JS (window.__photos__ или похожее) ---")
try:
    js_result = driver.execute_script("""
        var imgs = [];
        document.querySelectorAll('img').forEach(function(img) {
            var s = img.src || img.dataset.src || img.dataset.lazy || '';
            if (s && s.startsWith('http') && !s.includes('.svg')) imgs.push(s);
        });
        return imgs;
    """)
    print(f"JS img: {len(js_result)}")
    for p in js_result[:20]:
        print(f"  {p}")
except Exception as e:
    print(f"JS ошибка: {e}")

input("\nНажми Enter чтобы закрыть...")
driver.quit()

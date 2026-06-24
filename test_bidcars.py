"""
Запусти: python test_bidcars.py
"""
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

print("Открываю bid.cars через undetected-chromedriver...")
options = uc.ChromeOptions()
options.add_argument("--window-size=1920,1080")

driver = uc.Chrome(options=options, version_main=149)

def click(el):
    driver.execute_script("arguments[0].click();", el)

driver.get("https://bid.cars/en/search")
time.sleep(6)

print(f"Заголовок: {driver.title}")
driver.save_screenshot("step1_loaded.png")
print("Скриншот step1_loaded.png")

if "проверяем" in driver.title.lower() or "checking" in driver.title.lower():
    print("Всё ещё показывает проверку, ждём ещё...")
    time.sleep(10)
    driver.save_screenshot("step1b_waiting.png")

print(f"Заголовок после ожидания: {driver.title}")

# Шаг 1: Выбираем Type = Automobile
print("\nШаг 1: Выбираем тип Automobile...")
try:
    type_btn = driver.find_element(By.CSS_SELECTOR, ".search_make_transport .dropdown-toggle")
    click(type_btn)
    time.sleep(1)
    automobile = driver.find_element(By.XPATH, "//a[contains(@class,'dropdown-item') and contains(text(),'Automobile')]")
    click(automobile)
    time.sleep(2)
    print("  ✅ Тип выбран!")
except Exception as e:
    print(f"  ❌ Ошибка: {e}")
    driver.save_screenshot("error_type.png")

driver.save_screenshot("step2_type_selected.png")

# Шаг 2: Выбираем марку Toyota
print("\nШаг 2: Выбираем марку Toyota...")
try:
    make_btn = driver.find_element(By.CSS_SELECTOR, ".search_make_filter .dropdown-toggle")
    click(make_btn)
    time.sleep(1)
    toyota = driver.find_element(By.XPATH, "//a[contains(@class,'dropdown-item') and text()='Toyota']")
    click(toyota)
    time.sleep(2)
    print("  ✅ Марка выбрана!")
except Exception as e:
    print(f"  ❌ Ошибка: {e}")
    driver.save_screenshot("error_make.png")

# Шаг 3: Нажимаем Search
print("\nШаг 3: Нажимаем Search...")
try:
    search_btn = driver.find_element(By.CSS_SELECTOR, "button.btn-primary[type='submit']")
    click(search_btn)
    time.sleep(7)
    print(f"  URL: {driver.current_url}")
except Exception as e:
    print(f"  ❌ Ошибка: {e}")

driver.save_screenshot("step4_results.png")
print("Скриншот step4_results.png")

# Ищем лоты
lot_links = [a.get_attribute("href") for a in driver.find_elements(By.TAG_NAME, "a") if "/lot" in (a.get_attribute("href") or "")]
print(f"\nНайдено ссылок на лоты: {len(lot_links)}")
for l in lot_links[:5]:
    print(f"  {l}")

imgs = [i.get_attribute("src") or i.get_attribute("data-src") or "" for i in driver.find_elements(By.TAG_NAME, "img")]
car_imgs = [s for s in imgs if s and "http" in s and not any(x in s for x in [".svg", "flag", "logo", "icon", "facebook", "instagram"])]
print(f"\nФото авто: {len(car_imgs)}")
for img in car_imgs[:5]:
    print(f"  {img[:120]}")

input("\nНажми Enter чтобы закрыть...")
driver.quit()

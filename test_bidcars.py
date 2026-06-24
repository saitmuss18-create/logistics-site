"""
Запусти: python test_bidcars.py
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
options.add_argument("--window-size=1920,1080")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

print("Открываю bid.cars...")
driver.get("https://bid.cars/en/search")
time.sleep(5)

driver.save_screenshot("step1_loaded.png")
print("Скриншот step1_loaded.png сохранён")

# Ищем дропдаун марки
print("\nИщем поле выбора марки...")
try:
    # Пробуем найти select или кнопку с "All makes"
    make_selects = driver.find_elements(By.TAG_NAME, "select")
    print(f"Найдено select элементов: {len(make_selects)}")
    for i, sel in enumerate(make_selects):
        print(f"  select[{i}]: id={sel.get_attribute('id')} name={sel.get_attribute('name')} — options: {len(sel.find_elements(By.TAG_NAME, 'option'))}")

    make_buttons = driver.find_elements(By.XPATH, "//*[contains(text(), 'All makes') or contains(text(), 'make')]")
    print(f"Кнопок 'All makes': {len(make_buttons)}")
    for b in make_buttons[:3]:
        print(f"  tag={b.tag_name} text='{b.text[:40]}' class='{b.get_attribute('class')[:50]}'")

except Exception as e:
    print(f"Ошибка: {e}")

# Пробуем кликнуть на "All makes"
print("\nПробуем выбрать Toyota...")
try:
    # Вариант 1: через select
    from selenium.webdriver.support.ui import Select
    selects = driver.find_elements(By.TAG_NAME, "select")
    for sel in selects:
        opts = sel.find_elements(By.TAG_NAME, "option")
        opt_texts = [o.text for o in opts]
        if any("Toyota" in t for t in opt_texts):
            print(f"Нашли select с Toyota! options: {opt_texts[:5]}")
            Select(sel).select_by_visible_text("Toyota")
            time.sleep(2)
            break

    # Вариант 2: кликнуть на текст All makes и выбрать
    all_makes = driver.find_elements(By.XPATH, "//*[contains(@class,'make') or contains(@placeholder,'make') or contains(text(),'All makes')]")
    for el in all_makes[:3]:
        print(f"  Элемент: tag={el.tag_name} text='{el.text[:30]}' class='{el.get_attribute('class')[:50]}'")
        try:
            el.click()
            time.sleep(2)
            driver.save_screenshot("step2_clicked_make.png")
            print("  Кликнули! Скриншот step2_clicked_make.png")

            toyota_opt = driver.find_elements(By.XPATH, "//*[contains(text(),'Toyota')]")
            print(f"  Опций Toyota: {len(toyota_opt)}")
            if toyota_opt:
                toyota_opt[0].click()
                time.sleep(2)
                print("  Выбрали Toyota!")
            break
        except:
            pass

except Exception as e:
    print(f"Ошибка выбора: {e}")

driver.save_screenshot("step3_after_make.png")
print("\nСкриншот step3_after_make.png")

# Нажать кнопку Search
print("\nИщем кнопку Search...")
try:
    search_btns = driver.find_elements(By.XPATH, "//button[contains(text(),'Search') or contains(@class,'search')]")
    print(f"Кнопок Search: {len(search_btns)}")
    for btn in search_btns[:3]:
        print(f"  '{btn.text}' class='{btn.get_attribute('class')[:40]}'")
    if search_btns:
        search_btns[0].click()
        time.sleep(5)
        print("Нажали Search!")
        driver.save_screenshot("step4_results.png")
        print("Скриншот step4_results.png")
except Exception as e:
    print(f"Ошибка поиска: {e}")

print(f"\nURL после поиска: {driver.current_url}")

# Ссылки на лоты
lot_links = [a.get_attribute("href") for a in driver.find_elements(By.TAG_NAME, "a") if "/lot" in (a.get_attribute("href") or "")]
print(f"Ссылок на лоты: {len(lot_links)}")
for l in lot_links[:5]:
    print(f"  {l}")

input("\nНажми Enter чтобы закрыть...")
driver.quit()

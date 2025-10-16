import argparse
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def scroll_down(driver):
    """Автоскролл страницы до конца для подгрузки элементов."""
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def extract_details(card):
    """Извлекает название, цену, ссылку и RAM."""
    try:
        title_element = card.find_element(By.CSS_SELECTOR, "a.item-card__name")
        title = title_element.text.strip()
        url = title_element.get_attribute("href")
    except:
        title, url = "Название: не указано", "Ссылка: не указана"

    try:
        price = card.find_element(By.CSS_SELECTOR, "span.item-card__prices-price").text.strip()
    except:
        price = "Цена: не указана"

    ram = "Характеристики: не указано"
    try:
        props = card.find_elements(By.CSS_SELECTOR, "span.item-card__properties-value")
        for p in props:
            if "Гб" in p.text or "GB" in p.text:
                ram = p.text.strip()
    except:
        pass

    return title, price, url, ram

def parse_all_pages(start_url, headless):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)
    driver.get(start_url)

    all_results = []
    page = 1

    while True:
        print(f"▶ Страница {page}: сканирую...")
        scroll_down(driver)
        time.sleep(1)

        cards = driver.find_elements(By.CSS_SELECTOR, "div.item-card")
        print(f"  Найдено карточек: {len(cards)}")

        for card in cards:
            data = extract_details(card)
            all_results.append(data)

        try:
            next_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label='Следующая страница']"))
            )
            actions = ActionChains(driver)
            actions.move_to_element(next_button).click().perform()
            page += 1
            time.sleep(2)
        except:
            print("◼ Конец страниц, выходим.")
            break

    driver.quit()
    return all_results

def save_results(items, filename="kaspi_output.txt"):
    with open(filename, "w", encoding="utf-8") as file:
        for title, price, url, ram in items:
            file.write(f"{title} | {price} | {url} | {ram}\n")
    print(f"\nГотово. Сохранено: {len(items)} товаров. Файл: {filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="URL первой страницы категории")
    parser.add_argument("--headless", action="store_true", help="Запустить без окна браузера")
    args = parser.parse_args()

    results = parse_all_pages(args.url, args.headless)
    save_results(results)

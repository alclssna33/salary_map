"""봉직의 선택 후 화면 스크린샷"""
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import time

opts = Options()
opts.add_argument('--headless')
opts.add_argument('--no-sandbox')
opts.add_argument('--disable-dev-shm-usage')
opts.add_argument('--window-size=1400,1800')

driver = webdriver.Chrome(options=opts)
driver.get('http://localhost:8501')
time.sleep(10)

try:
    wait = WebDriverWait(driver, 15)

    # Streamlit selectbox: data-baseweb="select" 컨테이너
    dropdowns = driver.find_elements(By.CSS_SELECTOR, "[data-baseweb='select']")
    print(f"드롭다운 수: {len(dropdowns)}")

    if len(dropdowns) >= 3:
        # 세 번째 = 고용형태
        emp_dropdown = dropdowns[2]
        emp_dropdown.click()
        time.sleep(1)

        # 리스트에서 '봉직의' 텍스트 찾아 클릭
        options = driver.find_elements(By.CSS_SELECTOR, "[role='option']")
        for opt in options:
            if '봉직의' in opt.text:
                opt.click()
                print("봉직의 클릭 완료")
                break
        time.sleep(5)

    driver.save_screenshot("screenshot_bongji.png")
    print("저장 완료")

except Exception as e:
    print(f"오류: {e}")
    driver.save_screenshot("screenshot_bongji.png")

driver.quit()

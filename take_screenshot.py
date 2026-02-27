from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import time

opts = Options()
opts.add_argument('--headless')
opts.add_argument('--no-sandbox')
opts.add_argument('--disable-dev-shm-usage')
opts.add_argument('--window-size=1400,1800')

driver = webdriver.Chrome(options=opts)

# ── 1) 기본 화면 스크린샷 ─────────────────────────────────────────────────
driver.get('http://localhost:8501')
time.sleep(10)
driver.save_screenshot("screenshot_full.png")
print("기본 화면 저장 완료")

# ── 2) 막대그래프 클릭 → 팝업 스크린샷 ──────────────────────────────────
# Plotly 캔버스(SVG) 안의 막대 rect 요소를 찾아 클릭
try:
    # Plotly 차트가 iframe 없이 직접 렌더링되므로 SVG rect 탐색
    wait = WebDriverWait(driver, 15)

    # Plotly bar는 <g class="bars"> 안의 <g class="points"> > <path> 또는 <rect>
    # 가장 큰 막대(2026-02, 중앙 정도)를 클릭
    bars = wait.until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "g.bars .point path, g.bar .point path")
        )
    )
    if bars:
        # 마지막 막대(최신 월) 클릭
        target = bars[-1]
        driver.execute_script("arguments[0].scrollIntoView(true);", target)
        time.sleep(1)
        ActionChains(driver).move_to_element(target).click().perform()
        print(f"막대 클릭 완료 (총 {len(bars)}개 막대 중 마지막)")
        time.sleep(6)  # 다이얼로그 로딩 대기
        driver.save_screenshot("screenshot_dialog.png")
        print("팝업 화면 저장 완료")
    else:
        print("막대 요소를 찾지 못했습니다.")
except Exception as e:
    print(f"클릭 실패: {e}")
    driver.save_screenshot("screenshot_click_failed.png")

driver.quit()

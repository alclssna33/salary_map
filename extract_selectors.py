"""
실제 페이지에서 CSS Selector를 추출하는 스크립트
브라우저 개발자 도구에서 확인한 정보를 바탕으로 작성
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import json
import time

MAIN_URL = "https://www.medigate.net/"
RECRUIT_URL = "https://www.medigate.net/recruit"
USER_ID = "bassdoctor"
USER_PW = "!1q2w3e4r5t"

def setup_driver():
    """Selenium WebDriver 설정"""
    chrome_options = Options()
    # 브라우저 창 표시 (디버깅용)
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.maximize_window()
        return driver
    except Exception as e:
        print(f"ChromeDriver 설정 실패: {e}")
        return None

def login(driver):
    """로그인"""
    print("메인 페이지 접속 중...")
    driver.get(MAIN_URL)
    time.sleep(2)
    
    # 아이디 입력
    try:
        id_input = driver.find_element(By.CSS_SELECTOR, "input[name='usrIdT']")
        id_input.send_keys(USER_ID)
        time.sleep(0.5)
        
        pw_input = driver.find_element(By.CSS_SELECTOR, "input[name='usrPasswdT']")
        pw_input.send_keys(USER_PW)
        time.sleep(0.5)
        
        # 로그인 버튼 클릭
        login_btn = driver.find_element(By.CSS_SELECTOR, "button.button.type1[onclick*='checkLoginForm']")
        login_btn.click()
        time.sleep(5)
        
        print("로그인 완료")
        return True
    except Exception as e:
        print(f"로그인 실패: {e}")
        return False

def analyze_recruit_page(driver):
    """구인 공고 페이지 상세 분석"""
    print(f"\n구인 공고 페이지 접속: {RECRUIT_URL}")
    driver.get(RECRUIT_URL)
    time.sleep(5)  # 페이지 로딩 대기
    
    # 페이지 소스 저장
    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')
    
    with open('recruit_page_detailed.html', 'w', encoding='utf-8') as f:
        f.write(soup.prettify())
    print("페이지 HTML 저장: recruit_page_detailed.html")
    
    analysis = {
        'url': RECRUIT_URL,
        'title': driver.title,
        'selectors': {}
    }
    
    # 테이블 구조 확인
    print("\n=== 테이블 구조 분석 ===")
    tables = soup.find_all('table')
    print(f"발견된 테이블 수: {len(tables)}")
    
    for i, table in enumerate(tables):
        print(f"\n테이블 {i+1}:")
        print(f"  클래스: {table.get('class', [])}")
        print(f"  ID: {table.get('id', '')}")
        
        # 테이블 헤더 확인
        thead = table.find('thead')
        if thead:
            headers = thead.find_all('th')
            print(f"  헤더 컬럼 수: {len(headers)}")
            for j, header in enumerate(headers):
                print(f"    컬럼 {j+1}: {header.get_text(strip=True)}")
        
        # 테이블 바디 확인
        tbody = table.find('tbody')
        if tbody:
            rows = tbody.find_all('tr', limit=3)
            print(f"  데이터 행 수 (샘플): {len(rows)}")
            
            if rows:
                first_row = rows[0]
                cells = first_row.find_all(['td', 'th'])
                print(f"  첫 번째 행의 셀 수: {len(cells)}")
                for j, cell in enumerate(cells):
                    text = cell.get_text(strip=True)
                    print(f"    셀 {j+1}: {text[:50]}")
                    
                    # 링크 확인
                    link = cell.find('a')
                    if link:
                        print(f"      -> 링크: {link.get('href', '')}")
                        print(f"      -> 링크 텍스트: {link.get_text(strip=True)[:50]}")
    
    # 리스트 구조 확인
    print("\n=== 리스트 구조 분석 ===")
    lists = soup.find_all(['ul', 'ol'], class_=lambda x: x and 'list' in ' '.join(x).lower())
    print(f"발견된 리스트 수: {len(lists)}")
    
    for i, list_elem in enumerate(lists[:5]):
        print(f"\n리스트 {i+1}:")
        print(f"  클래스: {list_elem.get('class', [])}")
        print(f"  ID: {list_elem.get('id', '')}")
        
        items = list_elem.find_all('li', limit=3)
        print(f"  아이템 수 (샘플): {len(items)}")
        
        if items:
            first_item = items[0]
            print(f"  첫 번째 아이템 구조:")
            print(f"    클래스: {first_item.get('class', [])}")
            print(f"    ID: {first_item.get('id', '')}")
            print(f"    텍스트: {first_item.get_text(strip=True)[:100]}")
    
    # 주요 div 구조 확인
    print("\n=== 주요 div 구조 분석 ===")
    main_divs = soup.find_all('div', class_=lambda x: x and any(keyword in ' '.join(x).lower() for keyword in ['list', 'table', 'recruit', 'board', 'content']), limit=10)
    
    for i, div in enumerate(main_divs):
        print(f"\nDiv {i+1}:")
        print(f"  클래스: {div.get('class', [])}")
        print(f"  ID: {div.get('id', '')}")
    
    # 결과 저장
    with open('selector_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    
    print("\n분석 완료! 브라우저를 닫지 말고 개발자 도구(F12)로 직접 확인하세요.")
    input("확인 완료 후 Enter를 누르세요...")
    
    return analysis

def main():
    driver = setup_driver()
    if not driver:
        return
    
    try:
        if login(driver):
            analyze_recruit_page(driver)
    except Exception as e:
        print(f"오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()

if __name__ == '__main__':
    main()

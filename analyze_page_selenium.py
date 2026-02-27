"""
메디게이트 페이지 구조 분석 스크립트 (Selenium 버전)
로그인 후 실제 HTML 구조를 분석하여 CSS Selector를 추출합니다.
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import json
import time

# 로그인 정보
MAIN_URL = "https://www.medigate.net/"
RECRUIT_URL = "https://www.medigate.net/recruit"
USER_ID = "bassdoctor"
USER_PW = "!1q2w3e4r5t"

def setup_driver():
    """Selenium WebDriver 설정"""
    chrome_options = Options()
    # headless 모드 주석 처리 (브라우저 창을 보면서 디버깅 가능)
    # chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.maximize_window()  # 창 최대화
        return driver
    except Exception as e:
        print(f"ChromeDriver 설정 실패: {e}")
        print("ChromeDriver가 설치되어 있는지 확인하세요.")
        print("Chrome 브라우저가 설치되어 있어야 합니다.")
        return None

def login(driver):
    """로그인 처리 - 메인 페이지에서 로그인"""
    print("메인 페이지 접속 중...")
    driver.get(MAIN_URL)
    time.sleep(3)
    
    try:
        # 페이지 소스 저장 (디버깅용)
        with open('main_page_before_login.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print("메인 페이지 HTML 저장 완료: main_page_before_login.html")
        
        # 로그인 모달이나 폼 찾기
        # 여러 방법으로 시도
        id_input = None
        pw_input = None
        
        # 방법 1: 모든 input 필드 찾아서 확인
        all_inputs = driver.find_elements(By.TAG_NAME, "input")
        print(f"\n발견된 input 필드 수: {len(all_inputs)}")
        
        for inp in all_inputs:
            inp_type = inp.get_attribute('type')
            inp_name = inp.get_attribute('name')
            inp_id = inp.get_attribute('id')
            inp_class = inp.get_attribute('class')
            
            print(f"  input - type: {inp_type}, name: {inp_name}, id: {inp_id}, class: {inp_class}")
            
            # 아이디 필드 찾기
            if not id_input:
                if (inp_type == 'text' or inp_type == 'email') and (
                    'id' in (inp_name or '').lower() or 
                    'user' in (inp_name or '').lower() or
                    'id' in (inp_id or '').lower() or
                    'user' in (inp_id or '').lower()
                ):
                    id_input = inp
                    print(f"    -> 아이디 필드로 선택: {inp_name or inp_id}")
            
            # 비밀번호 필드 찾기
            if not pw_input:
                if inp_type == 'password':
                    pw_input = inp
                    print(f"    -> 비밀번호 필드로 선택: {inp_name or inp_id}")
        
        # 방법 2: 특정 선택자로 찾기
        if not id_input:
            id_selectors = [
                "input[name='userId']",
                "input[name='id']",
                "input[id='userId']",
                "input[id='id']",
                "input[type='text']",
                "#userId",
                "#id",
            ]
            
            for selector in id_selectors:
                try:
                    id_input = driver.find_element(By.CSS_SELECTOR, selector)
                    if id_input:
                        print(f"아이디 필드 발견: {selector}")
                        break
                except:
                    continue
        
        if not id_input:
            print("\n아이디 입력 필드를 찾을 수 없습니다.")
            print("페이지의 모든 input 요소를 확인했습니다.")
            return False
        
        if not pw_input:
            pw_selectors = [
                "input[name='userPw']",
                "input[name='password']",
                "input[type='password']",
                "#userPw",
                "#password",
            ]
            
            for selector in pw_selectors:
                try:
                    pw_input = driver.find_element(By.CSS_SELECTOR, selector)
                    if pw_input:
                        print(f"비밀번호 필드 발견: {selector}")
                        break
                except:
                    continue
        
        if not pw_input:
            print("\n비밀번호 입력 필드를 찾을 수 없습니다.")
            return False
        
        # 로그인 정보 입력
        print("\n로그인 정보 입력 중...")
        id_input.clear()
        id_input.send_keys(USER_ID)
        time.sleep(0.5)
        
        pw_input.clear()
        pw_input.send_keys(USER_PW)
        time.sleep(0.5)
        
        # 로그인 버튼 찾기 및 클릭
        print("로그인 버튼 찾는 중...")
        login_button = None
        
        # 모든 button 요소 확인
        all_buttons = driver.find_elements(By.TAG_NAME, "button")
        print(f"발견된 button 요소 수: {len(all_buttons)}")
        
        for btn in all_buttons:
            btn_text = btn.text
            btn_type = btn.get_attribute('type')
            btn_class = btn.get_attribute('class')
            print(f"  button - text: {btn_text[:20]}, type: {btn_type}, class: {btn_class}")
            
            if '로그인' in btn_text or btn_type == 'submit':
                login_button = btn
                print(f"    -> 로그인 버튼으로 선택")
                break
        
        if not login_button:
            login_button_selectors = [
                "button[type='submit']",
                "input[type='submit']",
                "button:contains('로그인')",
                ".login-btn",
                "#loginBtn",
                "button.login",
            ]
            
            for selector in login_button_selectors:
                try:
                    login_button = driver.find_element(By.CSS_SELECTOR, selector)
                    if login_button:
                        print(f"로그인 버튼 발견: {selector}")
                        break
                except:
                    continue
        
        if login_button:
            login_button.click()
            print("로그인 버튼 클릭")
        else:
            # Enter 키로 시도
            print("로그인 버튼을 찾지 못해 Enter 키로 시도")
            pw_input.send_keys("\n")
        
        time.sleep(5)  # 로그인 처리 대기 시간 증가
        
        # 로그인 후 페이지 저장
        with open('main_page_after_login.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print("로그인 후 페이지 HTML 저장 완료: main_page_after_login.html")
        
        # 로그인 성공 확인
        current_url = driver.current_url
        page_source = driver.page_source.lower()
        
        # 로그인 실패 표시가 있는지 확인
        if '아이디' in page_source and '비밀번호' in page_source and '틀렸' in page_source:
            print("로그인 실패: 아이디 또는 비밀번호가 틀렸습니다.")
            return False
        
        # 로그인 성공 여부 확인
        if '로그아웃' in page_source or '마이페이지' in page_source or USER_ID in page_source:
            print("로그인 성공!")
            return True
        else:
            print(f"로그인 상태 불명확. 현재 URL: {current_url}")
            return True  # 일단 진행 시도
            
    except Exception as e:
        print(f"로그인 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False

def analyze_recruit_page(driver):
    """구인 공고 페이지 분석"""
    print(f"\n구인 공고 페이지 접속 중: {RECRUIT_URL}")
    driver.get(RECRUIT_URL)
    time.sleep(3)
    
    # 페이지 소스 가져오기
    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')
    
    print("\n=== 페이지 구조 분석 ===")
    
    # HTML 구조 저장 (디버깅용)
    with open('recruit_page.html', 'w', encoding='utf-8') as f:
        f.write(soup.prettify())
    print("페이지 HTML 저장 완료: recruit_page.html")
    
    analysis = {
        'url': RECRUIT_URL,
        'title': driver.title,
        'structure': {}
    }
    
    # 공고 리스트 컨테이너 찾기
    print("\n1. 공고 리스트 컨테이너 찾기...")
    list_selectors = [
        ('table', {}),
        ('ul', {'class': lambda x: x and 'list' in ' '.join(x).lower()}),
        ('div', {'class': lambda x: x and 'list' in ' '.join(x).lower()}),
        ('div', {'id': lambda x: x and 'list' in x.lower()}),
    ]
    
    list_container = None
    for tag, attrs in list_selectors:
        container = soup.find(tag, attrs)
        if container:
            list_container = container
            print(f"   발견: {tag} - 클래스: {container.get('class', [])}")
            break
    
    if not list_container:
        print("   공고 리스트 컨테이너를 찾지 못했습니다.")
        # 테이블이 있는지 확인
        tables = soup.find_all('table')
        if tables:
            print(f"   테이블 {len(tables)}개 발견")
            list_container = tables[0]
    
    # 공고 아이템 찾기
    print("\n2. 공고 아이템 찾기...")
    items = []
    
    if list_container:
        # 테이블인 경우
        if list_container.name == 'table':
            items = list_container.find_all('tr')[1:]  # 헤더 제외
            if items:
                print(f"   테이블 행 {len(items)}개 발견")
        else:
            # 리스트인 경우
            items = list_container.find_all('li', limit=10)
            if not items:
                items = list_container.find_all('div', {'class': lambda x: x and ('item' in ' '.join(x).lower() or 'post' in ' '.join(x).lower())}, limit=10)
    
    if not items:
        # 전체 페이지에서 찾기
        items = soup.find_all('tr', limit=10)
        if not items:
            items = soup.find_all('div', {'class': lambda x: x and 'item' in ' '.join(x).lower()}, limit=10)
    
    if not items:
        print("   공고 아이템을 찾지 못했습니다.")
        print("   페이지의 주요 구조를 확인합니다...")
        # 주요 요소 출력
        main_elements = soup.find_all(['table', 'ul', 'div'], limit=20)
        for elem in main_elements:
            classes = elem.get('class', [])
            elem_id = elem.get('id', '')
            if classes or elem_id:
                print(f"   {elem.name}: 클래스={classes}, ID={elem_id}")
        return analysis
    
    print(f"   공고 아이템 {len(items)}개 발견")
    
    # 첫 번째 아이템 상세 분석
    print("\n3. 첫 번째 공고 아이템 상세 분석...")
    first_item = items[0]
    
    # HTML 구조 저장
    with open('first_item.html', 'w', encoding='utf-8') as f:
        f.write(first_item.prettify())
    print("   첫 번째 아이템 HTML 저장 완료: first_item.html")
    
    # 각 필드 추출
    fields_to_find = {
        'title': ['제목', 'title', 'subject'],
        'hospital': ['병원', 'hospital', 'company', '의원'],
        'specialty': ['전공', 'specialty', 'dept', '과'],
        'region': ['지역', 'location', 'region', '서울', '부산', '경기'],
        'register_date': ['등록', 'register', 'created', '작성'],
        'deadline_date': ['마감', 'deadline', 'end', '종료'],
    }
    
    # 테이블인 경우
    if first_item.name == 'tr':
        cells = first_item.find_all(['td', 'th'])
        print(f"\n   테이블 셀 {len(cells)}개 발견")
        for i, cell in enumerate(cells):
            text = cell.get_text(strip=True)
            if text:
                print(f"   셀 {i+1}: {text[:50]}")
                analysis['structure'][f'cell_{i+1}'] = {
                    'text': text[:100],
                    'html': str(cell)[:200],
                    'selector': generate_selector(cell)
                }
    else:
        # 각 필드 찾기
        for field_name, keywords in fields_to_find.items():
            print(f"\n   {field_name} 찾기...")
            found = False
            
            for keyword in keywords:
                # 클래스명에 키워드가 포함된 요소 찾기
                for elem in first_item.find_all(['span', 'div', 'td', 'a', 'p']):
                    classes = ' '.join(elem.get('class', [])).lower()
                    text = elem.get_text(strip=True)
                    
                    if keyword.lower() in classes or (text and any(k in text for k in keywords if len(k) > 2)):
                        if text and len(text) > 2:
                            analysis['structure'][field_name] = {
                                'tag': elem.name,
                                'classes': elem.get('class', []),
                                'text': text[:100],
                                'selector': generate_selector(elem)
                            }
                            print(f"      발견: {elem.name}.{'.'.join(elem.get('class', []))} - {text[:50]}")
                            found = True
                            break
                
                if found:
                    break
    
    # 분석 결과 저장
    with open('page_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    print("\n분석 결과 저장 완료: page_analysis.json")
    
    return analysis

def generate_selector(element):
    """요소로부터 CSS Selector 생성"""
    if element.get('id'):
        return f"#{element.get('id')}"
    
    classes = element.get('class', [])
    if classes:
        return f"{element.name}.{'.'.join(classes)}"
    
    return element.name

def main():
    """메인 실행 함수"""
    print("=" * 60)
    print("메디게이트 페이지 구조 분석 (Selenium 버전)")
    print("=" * 60)
    
    driver = setup_driver()
    if not driver:
        print("WebDriver 설정 실패")
        return
    
    try:
        # 로그인
        if not login(driver):
            print("로그인 실패")
            return
        
        # 페이지 분석
        analysis = analyze_recruit_page(driver)
        
        if analysis:
            print("\n" + "=" * 60)
            print("분석 완료!")
            print("=" * 60)
            print("\n생성된 파일:")
            print("  - recruit_page.html: 전체 페이지 HTML")
            print("  - first_item.html: 첫 번째 공고 아이템 HTML")
            print("  - page_analysis.json: 분석 결과 JSON")
        
    except Exception as e:
        print(f"\n오류 발생: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()
        print("\n브라우저 종료")

if __name__ == '__main__':
    main()

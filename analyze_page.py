"""
메디게이트 페이지 구조 분석 스크립트
로그인 후 실제 HTML 구조를 분석하여 CSS Selector를 추출합니다.
"""
import requests
from bs4 import BeautifulSoup
import json
from urllib.parse import urljoin

# 로그인 정보
LOGIN_URL = "https://new.medigate.net/user/member/login"
RECRUIT_URL = "https://new.medigate.net/recruit"
USER_ID = "bassdoctor"
USER_PW = "!1q2w3e4r5t"

def login_and_get_session():
    """로그인하여 세션을 생성합니다."""
    session = requests.Session()
    
    # User-Agent 설정
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    
    # 로그인 페이지 접속 (CSRF 토큰 등 필요한 정보 수집)
    print("로그인 페이지 접속 중...")
    login_page = session.get(LOGIN_URL)
    
    if login_page.status_code != 200:
        print(f"로그인 페이지 접속 실패: {login_page.status_code}")
        return None
    
    soup = BeautifulSoup(login_page.text, 'html.parser')
    
    # 로그인 폼 데이터 준비
    login_data = {
        'userId': USER_ID,
        'userPw': USER_PW,
    }
    
    # CSRF 토큰이나 hidden 필드가 있는지 확인
    csrf_token = soup.find('input', {'name': '_csrf'}) or soup.find('input', {'name': 'csrf_token'})
    if csrf_token:
        login_data[csrf_token.get('name')] = csrf_token.get('value')
    
    # 로그인 시도
    print("로그인 시도 중...")
    login_response = session.post(LOGIN_URL, data=login_data, allow_redirects=True)
    
    if login_response.status_code == 200:
        # 로그인 성공 여부 확인 (리다이렉트 또는 특정 텍스트 확인)
        if 'recruit' in login_response.url.lower() or '로그인' not in login_response.text:
            print("로그인 성공!")
            return session
        else:
            print("로그인 실패: 응답 내용 확인 필요")
            # 디버깅을 위해 응답 일부 출력
            print(f"응답 URL: {login_response.url}")
            print(f"응답 텍스트 일부: {login_response.text[:500]}")
            return None
    else:
        print(f"로그인 요청 실패: {login_response.status_code}")
        return None


def analyze_recruit_page(session):
    """구인 공고 페이지를 분석하여 구조를 파악합니다."""
    print(f"\n구인 공고 페이지 분석 중: {RECRUIT_URL}")
    
    response = session.get(RECRUIT_URL)
    
    if response.status_code != 200:
        print(f"페이지 접속 실패: {response.status_code}")
        return None
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # HTML 구조 분석
    print("\n=== 페이지 구조 분석 ===")
    
    # 공고 리스트 컨테이너 찾기
    print("\n1. 공고 리스트 컨테이너 찾기...")
    list_containers = [
        soup.find('div', class_=lambda x: x and 'list' in x.lower()),
        soup.find('ul', class_=lambda x: x and 'list' in x.lower()),
        soup.find('table'),
        soup.find('div', id=lambda x: x and 'list' in x.lower()),
    ]
    
    list_container = None
    for container in list_containers:
        if container:
            list_container = container
            print(f"   발견: {container.name}.{container.get('class', [])}")
            break
    
    if not list_container:
        print("   공고 리스트 컨테이너를 찾지 못했습니다.")
        print("   전체 HTML 구조를 확인합니다...")
        # 주요 div 구조 출력
        main_divs = soup.find_all('div', limit=20)
        for div in main_divs:
            classes = div.get('class', [])
            if classes:
                print(f"   div.{'.'.join(classes)}")
    
    # 공고 아이템 찾기
    print("\n2. 공고 아이템 찾기...")
    items = []
    
    # 다양한 패턴으로 시도
    item_patterns = [
        ('tr', {}),  # 테이블 행
        ('li', {}),  # 리스트 아이템
        ('div', {'class': lambda x: x and 'item' in ' '.join(x).lower()}),
        ('div', {'class': lambda x: x and 'post' in ' '.join(x).lower()}),
        ('div', {'class': lambda x: x and 'recruit' in ' '.join(x).lower()}),
    ]
    
    for tag, attrs in item_patterns:
        found_items = soup.find_all(tag, attrs, limit=10)
        if found_items:
            items = found_items
            print(f"   발견: {len(found_items)}개의 {tag} 요소")
            break
    
    if not items:
        print("   공고 아이템을 찾지 못했습니다.")
        return None
    
    # 첫 번째 아이템 상세 분석
    print("\n3. 첫 번째 공고 아이템 상세 분석...")
    first_item = items[0]
    
    analysis = {
        'item_tag': first_item.name,
        'item_classes': first_item.get('class', []),
        'item_id': first_item.get('id', ''),
        'structure': {}
    }
    
    # 제목 찾기
    print("\n   제목 찾기...")
    title_patterns = [
        ('a', {'class': lambda x: x and 'title' in ' '.join(x).lower()}),
        ('h3', {}),
        ('h2', {}),
        ('span', {'class': lambda x: x and 'title' in ' '.join(x).lower()}),
        ('td', {}),
        ('div', {'class': lambda x: x and 'title' in ' '.join(x).lower()}),
    ]
    
    for tag, attrs in title_patterns:
        title_elem = first_item.find(tag, attrs)
        if title_elem:
            title_text = title_elem.get_text(strip=True)
            if title_text and len(title_text) > 5:  # 의미있는 텍스트인지 확인
                analysis['structure']['title'] = {
                    'tag': tag,
                    'classes': title_elem.get('class', []),
                    'text': title_text[:50],
                    'selector': generate_selector(title_elem)
                }
                print(f"      발견: {tag}.{'.'.join(title_elem.get('class', []))} - {title_text[:50]}")
                break
    
    # 병원명 찾기
    print("\n   병원명 찾기...")
    hospital_patterns = [
        ('span', {'class': lambda x: x and ('hospital' in ' '.join(x).lower() or 'company' in ' '.join(x).lower())}),
        ('div', {'class': lambda x: x and ('hospital' in ' '.join(x).lower() or 'company' in ' '.join(x).lower())}),
        ('td', {}),
        ('span', {}),
    ]
    
    for tag, attrs in hospital_patterns:
        hospital_elem = first_item.find(tag, attrs)
        if hospital_elem:
            hospital_text = hospital_elem.get_text(strip=True)
            if hospital_text and ('병원' in hospital_text or '의원' in hospital_text or len(hospital_text) > 2):
                analysis['structure']['hospital'] = {
                    'tag': tag,
                    'classes': hospital_elem.get('class', []),
                    'text': hospital_text[:50],
                    'selector': generate_selector(hospital_elem)
                }
                print(f"      발견: {tag}.{'.'.join(hospital_elem.get('class', []))} - {hospital_text[:50]}")
                break
    
    # 전공 찾기
    print("\n   전공 찾기...")
    specialty_patterns = [
        ('span', {'class': lambda x: x and ('specialty' in ' '.join(x).lower() or 'dept' in ' '.join(x).lower() or 'major' in ' '.join(x).lower())}),
        ('div', {'class': lambda x: x and ('specialty' in ' '.join(x).lower() or 'dept' in ' '.join(x).lower())}),
        ('td', {}),
    ]
    
    for tag, attrs in specialty_patterns:
        specialty_elem = first_item.find(tag, attrs)
        if specialty_elem:
            specialty_text = specialty_elem.get_text(strip=True)
            if specialty_text and ('과' in specialty_text or len(specialty_text) > 1):
                analysis['structure']['specialty'] = {
                    'tag': tag,
                    'classes': specialty_elem.get('class', []),
                    'text': specialty_text[:50],
                    'selector': generate_selector(specialty_elem)
                }
                print(f"      발견: {tag}.{'.'.join(specialty_elem.get('class', []))} - {specialty_text[:50]}")
                break
    
    # 지역 찾기
    print("\n   지역 찾기...")
    region_patterns = [
        ('span', {'class': lambda x: x and ('location' in ' '.join(x).lower() or 'region' in ' '.join(x).lower() or 'area' in ' '.join(x).lower())}),
        ('div', {'class': lambda x: x and ('location' in ' '.join(x).lower() or 'region' in ' '.join(x).lower())}),
        ('td', {}),
    ]
    
    for tag, attrs in region_patterns:
        region_elem = first_item.find(tag, attrs)
        if region_elem:
            region_text = region_elem.get_text(strip=True)
            if region_text and ('서울' in region_text or '부산' in region_text or '경기' in region_text or '구' in region_text or '시' in region_text):
                analysis['structure']['region'] = {
                    'tag': tag,
                    'classes': region_elem.get('class', []),
                    'text': region_text[:50],
                    'selector': generate_selector(region_elem)
                }
                print(f"      발견: {tag}.{'.'.join(region_elem.get('class', []))} - {region_text[:50]}")
                break
    
    # 날짜 찾기
    print("\n   날짜 정보 찾기...")
    date_patterns = [
        ('span', {'class': lambda x: x and ('date' in ' '.join(x).lower() or 'day' in ' '.join(x).lower())}),
        ('div', {'class': lambda x: x and ('date' in ' '.join(x).lower())}),
        ('td', {}),
    ]
    
    date_elements = []
    for tag, attrs in date_patterns:
        found_dates = first_item.find_all(tag, attrs)
        for date_elem in found_dates:
            date_text = date_elem.get_text(strip=True)
            if date_text and ('202' in date_text or '2024' in date_text or '2025' in date_text or '-' in date_text or '.' in date_text):
                date_elements.append({
                    'tag': tag,
                    'classes': date_elem.get('class', []),
                    'text': date_text[:50],
                    'selector': generate_selector(date_elem)
                })
                print(f"      발견: {tag}.{'.'.join(date_elem.get('class', []))} - {date_text[:50]}")
    
    if date_elements:
        analysis['structure']['dates'] = date_elements
    
    # HTML 구조 일부 저장 (디버깅용)
    print("\n4. HTML 구조 일부 저장 중...")
    with open('page_structure.html', 'w', encoding='utf-8') as f:
        f.write(str(first_item.prettify()))
    print("   저장 완료: page_structure.html")
    
    return analysis


def generate_selector(element):
    """요소로부터 CSS Selector를 생성합니다."""
    selector_parts = []
    
    # ID가 있으면 ID 사용
    if element.get('id'):
        return f"#{element.get('id')}"
    
    # 클래스가 있으면 클래스 사용
    classes = element.get('class', [])
    if classes:
        class_selector = '.'.join(classes)
        tag_selector = f"{element.name}.{class_selector}"
        return tag_selector
    
    # 부모 요소 고려
    parent = element.parent
    if parent:
        parent_classes = parent.get('class', [])
        if parent_classes:
            return f"{parent.name}.{'.'.join(parent_classes)} > {element.name}"
    
    return element.name


def main():
    """메인 실행 함수"""
    print("=" * 60)
    print("메디게이트 페이지 구조 분석 시작")
    print("=" * 60)
    
    # 로그인
    session = login_and_get_session()
    if not session:
        print("\n로그인 실패. 스크립트를 종료합니다.")
        return
    
    # 페이지 분석
    analysis = analyze_recruit_page(session)
    
    if analysis:
        print("\n" + "=" * 60)
        print("분석 결과")
        print("=" * 60)
        print(json.dumps(analysis, indent=2, ensure_ascii=False))
        
        # 결과를 JSON 파일로 저장
        with open('page_analysis.json', 'w', encoding='utf-8') as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)
        print("\n분석 결과 저장 완료: page_analysis.json")
    else:
        print("\n페이지 분석 실패")
    
    print("\n분석 완료!")


if __name__ == '__main__':
    main()

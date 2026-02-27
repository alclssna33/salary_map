# 메디게이트 크롤링 설계 문서

## 1. 사이트 분석

### 대상 페이지
- URL: https://www.medigate.net/recruit
- 참고: 로그인이 필요한 페이지입니다. React 기반 동적 페이지이므로 Selenium 또는 Playwright 사용 필요
- 총 공고 수: 약 5,000건 이상 (페이지네이션 필요)

### 추출 대상 데이터
1. **제목** (Job Title) - 공고 설명/제목 텍스트
2. **병원명** (Hospital Name) - 병원/의원 이름
3. **병원 타입** (Hospital Type) - 의원, 종합병원, 병원, 네트워크의원 등
4. **전공** (Specialty/Department) - 여러 개의 전공 태그 (내과, 일반의, 영상의학과 등)
5. **고용 형태** (Employment Type) - 봉직의, 기타 등
6. **지역** (Location/Region) - 서울 서초구, 경기 남양주시 등
7. **등록일/시작일** (Start Date) - "(02/12 시작)" 형식
8. **마감일** (Deadline Date) - "~03/31", "D-9", "~02/28" 형식
9. **공고 URL** (Source URL) - 상세 페이지 링크
10. **공고 ID** (Source ID) - URL에서 추출 가능한 고유 ID

### 실제 CSS Selector (페이지 구조 분석 완료 - Phase 2)

**✅ 최종 확정된 데이터 구조 (Phase 2 완료):**

각 공고 행은 **4개의 열(Column)**로 구성되어 있으며, 각 열의 구조는 다음과 같습니다:

| 순서 | 감싸는 요소 | 상단 데이터 (my-10e3t97) | 하단 데이터 (my-1cqarh6) | 예시 데이터 |
|------|------------|------------------------|------------------------|------------|
| 1열 (왼쪽) | `div` | 병원명 | 병원 타입 | 명지병원 / 종합병원 |
| 2열 (중앙) | `button` | 공고 제목 (`span.my-80pqzf`) | 전공 태그 (`span.my-1n83qxm`) | 정형외과 임상강사 모집 / 정형외과 |
| 3열 (우측) | `div` | 고용 형태 | 상세 지역 | 전임의 / 경기 고양시 덕양구 |
| 4열 (끝) | `div` | 마감일/D-day | 시작일 | D-10 / 02/11 시작 |

**⚠️ 중요:** 
- 클래스명(`my-10e3t97`, `my-1cqarh6`)이 여러 열에서 중복 사용되므로, **반드시 자식 요소의 순서(index)**를 기준으로 데이터를 추출해야 합니다.
- 각 공고 행의 직접 자식 요소를 `children[0]`, `children[1]`, `children[2]`, `children[3]`로 접근하여 각 열을 구분합니다.

**페이지 구조 특징:**
- React 기반 동적 페이지 (CSR - Client Side Rendering)
- 카드/행 형식의 리스트 레이아웃
- 각 공고 아이템은 독립적인 카드 형태로 구성
- 페이지네이션 또는 무한 스크롤 방식 사용 가능

#### 최종 확정된 CSS Selector 및 데이터 매핑 (Phase 2 완료)

**데이터 항목, 위치 및 선택자, 예시 데이터:**

| 데이터 항목 | 위치 및 선택자 | 예시 데이터 |
|------------|--------------|------------|
| 병원명 | 1열(div) 내의 `span.my-10e3t97` | 명지병원 |
| 병원 타입 | 1열(div) 내의 `span.my-1cqarh6` | 종합병원 |
| 공고 제목 | 2열(button) 내의 `span.my-80pqzf` | 정형외과 임상강사 모집 |
| 전공 태그 | 2열(button) 내의 `span.my-1n83qxm` | 정형외과 |
| 고용 형태 | 3열(div) 내의 `span.my-10e3t97` | 전임의 |
| 지역 | 3열(div) 내의 `span.my-1cqarh6` | 경기 고양시 덕양구 |
| 마감일 | 4열(div) 내의 첫 번째 요소 | D-10, ~03/31 |
| 시작일 | 4열(div) 내의 두 번째 요소 | 02/11 시작 |

**파싱 가이드라인:**
1. 각 공고 행을 찾은 후, 직접 자식 요소를 순서대로 접근 (`children[0]`, `children[1]`, `children[2]`, `children[3]`)
2. **1열 (`children[0]`)**: `div` 요소
   - `span.my-10e3t97` → 병원명
   - `span.my-1cqarh6` → 병원 타입
3. **2열 (`children[1]`)**: `button` 요소
   - `span.my-80pqzf` → 공고 제목
   - `span.my-1n83qxm` → 전공 태그들 (여러 개 가능, `find_elements` 사용)
4. **3열 (`children[2]`)**: `div` 요소
   - `span.my-10e3t97` → 고용 형태
   - `span.my-1cqarh6` → 상세 지역
5. **4열 (`children[3]`)**: `div` 요소
   - 첫 번째 자식 요소 → 마감일/D-day
   - 두 번째 자식 요소 → 시작일

**⚠️ 주의:** 클래스명이 중복되므로 절대 클래스명만으로 찾지 말고, 반드시 열의 순서를 먼저 확인한 후 해당 열 내에서 선택자를 사용해야 합니다.

#### 실제 추출 시 고려사항

1. **React 동적 렌더링 대응**
   ```python
   # Selenium 사용 시
   from selenium.webdriver.support.ui import WebDriverWait
   from selenium.webdriver.support import expected_conditions as EC
   
   # 요소가 로드될 때까지 대기
   wait = WebDriverWait(driver, 10)
   items = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "공고아이템선택자")))
   ```

2. **페이지네이션 처리**
   ```python
   # 다음 페이지 버튼 또는 스크롤 처리
   # 무한 스크롤인 경우: driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
   ```

3. **데이터 추출 예시 구조 (최종 확정된 Selector 적용)**
   ```python
   # 각 공고 행에서 4개의 열을 순서대로 추출
   items = driver.find_elements(By.CSS_SELECTOR, "li")  # 또는 공고 행 선택자
   
   for item in items:
       try:
           # 각 공고 행의 자식 요소들을 순서대로 가져오기
           children = item.find_elements(By.XPATH, "./*")  # 직접 자식 요소들
           
           if len(children) < 4:
               continue  # 4개 열이 없으면 스킵
           
           # 1열 (div): 병원명, 병원 타입
           col1 = children[0]
           hospital_name = col1.find_element(By.CSS_SELECTOR, "span.my-10e3t97").text.strip()
           hospital_type = col1.find_element(By.CSS_SELECTOR, "span.my-1cqarh6").text.strip()
           
           # 2열 (button): 제목, 전공 태그
           col2 = children[1]
           title = col2.find_element(By.CSS_SELECTOR, "span.my-80pqzf").text.strip()
           specialty_tags = col2.find_elements(By.CSS_SELECTOR, "span.my-1n83qxm")
           specialties = [tag.text.strip() for tag in specialty_tags if tag.text.strip()]
           
           # 3열 (div): 고용 형태, 지역
           col3 = children[2]
           employment_type = col3.find_element(By.CSS_SELECTOR, "span.my-10e3t97").text.strip()
           location = col3.find_element(By.CSS_SELECTOR, "span.my-1cqarh6").text.strip()
           
           # 4열 (div): 마감일, 시작일
           col4 = children[3]
           col4_children = col4.find_elements(By.XPATH, "./*")
           deadline = col4_children[0].text.strip() if len(col4_children) > 0 else ""
           start_date = col4_children[1].text.strip() if len(col4_children) > 1 else ""
           
           print(f"병원명: {hospital_name} ({hospital_type})")
           print(f"제목: {title}")
           print(f"전공: {', '.join(specialties)}")
           print(f"고용 형태: {employment_type}")
           print(f"지역: {location}")
           print(f"마감일: {deadline}, 시작일: {start_date}")
           
       except Exception as e:
           print(f"아이템 파싱 오류: {e}")
           continue
   ```

#### 개발자 도구에서 실제 Selector 확인 방법

1. 브라우저에서 https://www.medigate.net/recruit 접속 (로그인 필요)
2. F12로 개발자 도구 열기
3. Elements 탭에서 각 요소 선택
4. 우클릭 → Copy → Copy selector
5. Console에서 테스트: `document.querySelector('복사한선택자')`
6. React DevTools 설치 시 컴포넌트 구조 확인 가능

#### 실제 크롤링 코드 예시 (Selenium 기반)

```python
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import re
from datetime import datetime

def crawl_medigate_recruit():
    """메디게이트 구인 공고 크롤링"""
    
    # WebDriver 설정
    chrome_options = Options()
    # chrome_options.add_argument('--headless')  # 필요시 주석 해제
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        # 로그인
        driver.get("https://www.medigate.net/")
        time.sleep(2)
        
        # 로그인 처리 (실제 필드명 확인 필요)
        id_input = driver.find_element(By.CSS_SELECTOR, "input[name='usrIdT']")
        id_input.send_keys("bassdoctor")
        
        pw_input = driver.find_element(By.CSS_SELECTOR, "input[name='usrPasswdT']")
        pw_input.send_keys("!1q2w3e4r5t")
        
        login_btn = driver.find_element(By.CSS_SELECTOR, "button.button.type1[onclick*='checkLoginForm']")
        login_btn.click()
        time.sleep(5)
        
        # 구인 공고 페이지 접속
        driver.get("https://www.medigate.net/recruit")
        time.sleep(5)  # React 렌더링 대기
        
        # 공고 아이템들이 로드될 때까지 대기
        wait = WebDriverWait(driver, 10)
        
        # 제목 요소가 나타날 때까지 대기 (확인된 Selector 사용)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "span.my-80pqzf")))
        
        # 공고 아이템 찾기 (li 또는 div - 실제 구조 확인 필요)
        # 방법 1: Selenium으로 직접 찾기
        # 공고 아이템의 부모 요소를 찾거나, 제목이 있는 요소의 부모를 찾기
        title_elements = driver.find_elements(By.CSS_SELECTOR, "span.my-80pqzf")
        
        results = []
        
        # 각 제목 요소의 부모(공고 아이템)를 찾아서 처리
        for title_elem in title_elements:
            try:
                # 제목 요소의 부모 요소를 공고 아이템으로 사용
                # 실제 구조에 따라 조정 필요 (li 또는 div)
                item = title_elem.find_element(By.XPATH, "./ancestor::li[1] | ./ancestor::div[contains(@class, 'item')][1]")
                
                # 제목 추출 (확인된 Selector 사용) ⭐
                title = title_elem.text.strip()
                
                # 전공 태그들 추출 (확인된 Selector 사용, 복수형) ⭐
                specialty_tags = item.find_elements(By.CSS_SELECTOR, "span.my-1n83qxm")
                specialties = [tag.text.strip() for tag in specialty_tags if tag.text.strip()]
                
                # 병원명 추출 (선택자 확인 필요)
                hospital_name = ""
                try:
                    # 실제 선택자로 교체 필요
                    hospital_elem = item.find_element(By.CSS_SELECTOR, "병원명선택자")
                    hospital_name = hospital_elem.text.strip()
                except:
                    pass
                
                # 지역 추출 (선택자 확인 필요)
                location = ""
                try:
                    # 실제 선택자로 교체 필요
                    location_elem = item.find_element(By.CSS_SELECTOR, "지역선택자")
                    location = location_elem.text.strip()
                except:
                    pass
                
                # 마감일 추출 (선택자 확인 필요)
                deadline = ""
                try:
                    # 실제 선택자로 교체 필요
                    deadline_elem = item.find_element(By.CSS_SELECTOR, "마감일선택자")
                    deadline = deadline_elem.text.strip()
                except:
                    pass
                
                # 시작일 추출 (선택자 확인 필요)
                start_date = ""
                try:
                    # 실제 선택자로 교체 필요 또는 정규표현식 사용
                    item_text = item.text
                    start_match = re.search(r'\((\d{2}/\d{2})\s*시작\)', item_text)
                    if start_match:
                        start_date = start_match.group(1)
                except:
                    pass
                
                # 공고 URL 추출
                source_url = ""
                source_id = ""
                try:
                    link_elem = item.find_element(By.CSS_SELECTOR, "a[href*='/recruit/']")
                    href = link_elem.get_attribute('href')
                    if href:
                        source_url = href if href.startswith('http') else f"https://www.medigate.net{href}"
                        # 공고 ID 추출 (URL에서)
                        match = re.search(r'/recruit/(\d+)', source_url)
                        if match:
                            source_id = match.group(1)
                except:
                    pass
                
                # 필수 필드 확인 (제목은 필수)
                if title:
                    results.append({
                        'title': title,
                        'hospital_name': hospital_name,
                        'specialty': ', '.join(specialties) if specialties else '',
                        'specialty_list': specialties,  # 리스트 형태로도 저장
                        'region': location,
                        'deadline_date': deadline,
                        'start_date': start_date,
                        'source_id': source_id,
                        'source_url': source_url,
                    })
                    
            except Exception as e:
                print(f"아이템 파싱 오류: {e}")
                continue
        
        return results
        
    finally:
        driver.quit()

# 사용 예시
if __name__ == '__main__':
    results = crawl_medigate_recruit()
    print(f"크롤링된 공고 수: {len(results)}")
    for i, result in enumerate(results[:5], 1):
        print(f"\n공고 {i}:")
        print(f"  제목: {result['title']}")
        print(f"  병원명: {result['hospital_name']}")
        print(f"  전공: {result['specialty']}")
        print(f"  전공 리스트: {result['specialty_list']}")
        print(f"  지역: {result['region']}")
        print(f"  마감일: {result['deadline_date']}")
        print(f"  시작일: {result['start_date']}")
        print(f"  공고 ID: {result['source_id']}")
        print(f"  URL: {result['source_url']}")
```

**✅ 모든 Selector 확인 완료 (Phase 2):**
- ✅ 병원명: `1열 div > span.my-10e3t97`
- ✅ 병원 타입: `1열 div > span.my-1cqarh6`
- ✅ 공고 제목: `2열 button > span.my-80pqzf`
- ✅ 전공 태그: `2열 button > span.my-1n83qxm`
- ✅ 고용 형태: `3열 div > span.my-10e3t97`
- ✅ 지역: `3열 div > span.my-1cqarh6`
- ✅ 마감일: `4열 div > 첫 번째 자식 요소`
- ✅ 시작일: `4열 div > 두 번째 자식 요소`

**구조:**
- 각 공고 행: `li` 또는 `div` 요소
- 4개의 직접 자식: `div`, `button`, `div`, `div` (순서대로)

#### BeautifulSoup을 사용한 대안 방법

Selenium과 함께 BeautifulSoup을 사용하면 더 유연한 파싱이 가능합니다:

```python
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time

def crawl_with_beautifulsoup():
    """BeautifulSoup을 사용한 크롤링 방법"""
    driver = webdriver.Chrome()
    
    try:
        # 로그인 및 페이지 접속 (위와 동일)
        # ... 로그인 코드 ...
        
        driver.get("https://www.medigate.net/recruit")
        time.sleep(5)
        
        # 페이지 소스 가져오기
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # 제목 요소들 찾기 (확인된 Selector 사용)
        title_elements = soup.select('span.my-80pqzf')
        
        results = []
        
        for title_elem in title_elements:
            try:
                # 제목 추출
                title = title_elem.get_text(strip=True)
                
                # 제목 요소의 부모 요소 찾기 (공고 아이템)
                # 방법 1: 가장 가까운 li 또는 div 찾기
                item = title_elem.find_parent('li')
                if not item:
                    item = title_elem.find_parent('div', class_=lambda x: x and 'item' in ' '.join(x).lower())
                
                if not item:
                    continue
                
                # 전공 태그들 추출 (확인된 Selector 사용)
                specialty_tags = item.select('span.my-1n83qxm')
                specialties = [tag.get_text(strip=True) for tag in specialty_tags if tag.get_text(strip=True)]
                
                # 다른 필드들 추출 (선택자 확인 후 추가)
                # ...
                
                if title:
                    results.append({
                        'title': title,
                        'specialty_list': specialties,
                        'specialty': ', '.join(specialties),
                        # ... 다른 필드들
                    })
                    
            except Exception as e:
                print(f"파싱 오류: {e}")
                continue
        
        return results
        
    finally:
        driver.quit()
```

**공고 아이템 찾기 팁:**
1. 제목 요소(`span.my-80pqzf`)의 부모 요소를 찾기
2. XPath 사용: `./ancestor::li[1]` 또는 `./ancestor::div[contains(@class, 'item')][1]`
3. BeautifulSoup의 `find_parent()` 메서드 사용
4. 개발자 도구에서 공고 아이템의 클래스명 확인 후 직접 선택

**⚠️ 주의사항:**
1. ✅ **제목과 전공 태그의 Selector는 확인 완료**: `span.my-80pqzf`, `span.my-1n83qxm`
2. ⚠️ **다른 필드들의 Selector는 아직 확인 필요**: 병원명, 지역, 마감일 등
3. React 페이지이므로 요소가 로드될 때까지 충분한 대기 시간이 필요합니다.
4. 페이지네이션 또는 무한 스크롤 처리가 필요할 수 있습니다 (총 5,057건).
5. 로그인 세션 유지 및 쿠키 관리가 필요합니다.
6. 공고 아이템 컨테이너의 정확한 선택자를 확인하면 더 효율적인 파싱이 가능합니다.

---

## 2. DB 모델링

### PostgreSQL용 models.py

```python
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class RegionCode(Base):
    """지역 코드 테이블"""
    __tablename__ = 'region_codes'
    
    code = Column(String(10), primary_key=True, comment='지역 코드 (예: 11010)')
    name = Column(String(100), nullable=False, comment='지역명 (예: 서울 강남구)')
    parent_code = Column(String(10), ForeignKey('region_codes.code'), nullable=True, comment='상위 지역 코드')
    level = Column(Integer, nullable=False, comment='지역 레벨 (1: 시도, 2: 시군구, 3: 읍면동)')
    created_at = Column(DateTime, default=datetime.now)
    
    # 인덱스
    __table_args__ = (
        Index('idx_region_name', 'name'),
    )


class SpecialtyCode(Base):
    """전공 코드 테이블"""
    __tablename__ = 'specialty_codes'
    
    code = Column(String(10), primary_key=True, comment='전공 코드 (예: 101)')
    name = Column(String(100), nullable=False, comment='전공명 (예: 내과)')
    category = Column(String(50), nullable=True, comment='전공 카테고리')
    created_at = Column(DateTime, default=datetime.now)
    
    # 인덱스
    __table_args__ = (
        Index('idx_specialty_name', 'name'),
    )


class JobPosting(Base):
    """구인 공고 테이블"""
    __tablename__ = 'job_postings'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 기본 정보
    title = Column(String(500), nullable=False, comment='공고 제목')
    hospital_name = Column(String(200), nullable=False, comment='병원명')
    
    # 코드화된 정보
    specialty_code = Column(String(10), ForeignKey('specialty_codes.code'), nullable=True, comment='전공 코드')
    region_code = Column(String(10), ForeignKey('region_codes.code'), nullable=True, comment='지역 코드')
    
    # 원본 데이터 (백업용)
    specialty_raw = Column(String(200), nullable=True, comment='원본 전공명')
    region_raw = Column(String(200), nullable=True, comment='원본 지역명')
    
    # 날짜 정보
    register_date = Column(Date, nullable=True, comment='등록일')
    deadline_date = Column(Date, nullable=True, comment='마감일')
    
    # 소스 정보
    source = Column(String(50), nullable=False, default='medigate', comment='데이터 출처 (medigate, 개비공 등)')
    source_id = Column(String(200), nullable=True, comment='원본 사이트의 공고 ID')
    source_url = Column(Text, nullable=True, comment='원본 공고 URL')
    
    # 추가 정보
    description = Column(Text, nullable=True, comment='공고 상세 내용')
    status = Column(String(20), default='active', comment='상태 (active, closed, expired)')
    
    # 메타 정보
    created_at = Column(DateTime, default=datetime.now, comment='DB 등록일시')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='DB 수정일시')
    crawled_at = Column(DateTime, nullable=True, comment='크롤링 일시')
    
    # 관계
    specialty = relationship('SpecialtyCode', foreign_keys=[specialty_code])
    region = relationship('RegionCode', foreign_keys=[region_code])
    
    # 인덱스
    __table_args__ = (
        Index('idx_source', 'source'),
        Index('idx_source_id', 'source', 'source_id'),
        Index('idx_specialty', 'specialty_code'),
        Index('idx_region', 'region_code'),
        Index('idx_deadline', 'deadline_date'),
        Index('idx_status', 'status'),
        Index('idx_created', 'created_at'),
    )


class CrawlLog(Base):
    """크롤링 로그 테이블"""
    __tablename__ = 'crawl_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False, comment='크롤링 소스')
    started_at = Column(DateTime, default=datetime.now, comment='크롤링 시작 시간')
    finished_at = Column(DateTime, nullable=True, comment='크롤링 종료 시간')
    status = Column(String(20), default='running', comment='상태 (running, success, failed)')
    items_crawled = Column(Integer, default=0, comment='크롤링된 항목 수')
    items_new = Column(Integer, default=0, comment='신규 항목 수')
    items_updated = Column(Integer, default=0, comment='업데이트된 항목 수')
    error_message = Column(Text, nullable=True, comment='에러 메시지')
```

### 초기 데이터 삽입 SQL (참고용)

```sql
-- 지역 코드 예시 데이터
INSERT INTO region_codes (code, name, parent_code, level) VALUES
('11', '서울특별시', NULL, 1),
('11010', '서울 강남구', '11', 2),
('11020', '서울 강동구', '11', 2),
('11030', '서울 강북구', '11', 2),
('11040', '서울 강서구', '11', 2),
('26', '부산광역시', NULL, 1),
('26010', '부산 해운대구', '26', 2),
('27', '대구광역시', NULL, 1),
('28', '인천광역시', NULL, 1),
('29', '광주광역시', NULL, 1),
('30', '대전광역시', NULL, 1),
('31', '울산광역시', NULL, 1),
('41', '경기도', NULL, 1),
('41010', '경기 수원시', '41', 2),
('41020', '경기 성남시', '41', 2);

-- 전공 코드 예시 데이터
INSERT INTO specialty_codes (code, name, category) VALUES
('101', '내과', '임상의학'),
('102', '외과', '임상의학'),
('103', '정형외과', '임상의학'),
('104', '신경외과', '임상의학'),
('105', '흉부외과', '임상의학'),
('106', '성형외과', '임상의학'),
('107', '마취과', '임상의학'),
('108', '산부인과', '임상의학'),
('109', '소아과', '임상의학'),
('110', '안과', '임상의학'),
('111', '이비인후과', '임상의학'),
('112', '피부과', '임상의학'),
('113', '비뇨의학과', '임상의학'),
('114', '정신건강의학과', '임상의학'),
('115', '재활의학과', '임상의학'),
('116', '영상의학과', '진단의학'),
('117', '병리과', '진단의학'),
('118', '진단검사의학과', '진단의학'),
('119', '가정의학과', '임상의학'),
('120', '응급의학과', '임상의학');
```

---

## 3. 데이터 매핑 함수

### clean_data.py 초안

```python
"""
데이터 정제 및 코드 매핑 함수
"""
import re
from datetime import datetime
from typing import Optional, Dict, Tuple


# 지역명 → 지역 코드 매핑 딕셔너리
REGION_MAPPING = {
    # 서울특별시
    '서울': '11',
    '서울특별시': '11',
    '서울 강남구': '11010',
    '서울 강동구': '11020',
    '서울 강북구': '11030',
    '서울 강서구': '11040',
    '서울 관악구': '11050',
    '서울 광진구': '11060',
    '서울 구로구': '11070',
    '서울 금천구': '11080',
    '서울 노원구': '11090',
    '서울 도봉구': '11100',
    '서울 동대문구': '11110',
    '서울 동작구': '11120',
    '서울 마포구': '11130',
    '서울 서대문구': '11140',
    '서울 서초구': '11150',
    '서울 성동구': '11160',
    '서울 성북구': '11170',
    '서울 송파구': '11180',
    '서울 양천구': '11190',
    '서울 영등포구': '11200',
    '서울 용산구': '11210',
    '서울 은평구': '11220',
    '서울 종로구': '11230',
    '서울 중구': '11240',
    '서울 중랑구': '11250',
    
    # 부산광역시
    '부산': '26',
    '부산광역시': '26',
    '부산 해운대구': '26010',
    '부산 남구': '26020',
    '부산 북구': '26030',
    '부산 사상구': '26040',
    '부산 사하구': '26050',
    '부산 서구': '26060',
    '부산 수영구': '26070',
    '부산 연제구': '26080',
    '부산 영도구': '26090',
    '부산 중구': '26100',
    '부산 강서구': '26110',
    '부산 금정구': '26120',
    '부산 기장군': '26130',
    '부산 동구': '26140',
    '부산 동래구': '26150',
    
    # 경기도
    '경기': '41',
    '경기도': '41',
    '경기 수원시': '41010',
    '경기 성남시': '41020',
    '경기 고양시': '41030',
    '경기 용인시': '41040',
    '경기 부천시': '41050',
    '경기 안산시': '41060',
    '경기 안양시': '41070',
    '경기 평택시': '41080',
    '경기 시흥시': '41090',
    '경기 김포시': '41100',
    '경기 광명시': '41110',
    '경기 이천시': '41120',
    '경기 양주시': '41130',
    '경기 오산시': '41140',
    '경기 구리시': '41150',
    '경기 안성시': '41160',
    '경기 포천시': '41170',
    '경기 의정부시': '41180',
    '경기 하남시': '41190',
    '경기 여주시': '41200',
    
    # 대구광역시
    '대구': '27',
    '대구광역시': '27',
    
    # 인천광역시
    '인천': '28',
    '인천광역시': '28',
    
    # 광주광역시
    '광주': '29',
    '광주광역시': '29',
    
    # 대전광역시
    '대전': '30',
    '대전광역시': '30',
    
    # 울산광역시
    '울산': '31',
    '울산광역시': '31',
    
    # 기타 시도
    '세종': '36',
    '세종특별자치시': '36',
    '강원': '42',
    '강원도': '42',
    '충북': '43',
    '충청북도': '43',
    '충남': '44',
    '충청남도': '44',
    '전북': '45',
    '전라북도': '45',
    '전남': '46',
    '전라남도': '46',
    '경북': '47',
    '경상북도': '47',
    '경남': '48',
    '경상남도': '48',
    '제주': '50',
    '제주특별자치도': '50',
}


# 전공명 → 전공 코드 매핑 딕셔너리
SPECIALTY_MAPPING = {
    '내과': '101',
    '외과': '102',
    '정형외과': '103',
    '정형외과의학과': '103',
    '신경외과': '104',
    '신경외과의학과': '104',
    '흉부외과': '105',
    '흉부외과의학과': '105',
    '성형외과': '106',
    '성형외과의학과': '106',
    '마취과': '107',
    '마취통증의학과': '107',
    '산부인과': '108',
    '산부인과의학과': '108',
    '소아과': '109',
    '소아청소년과': '109',
    '소아청소년과의학과': '109',
    '안과': '110',
    '안과의학과': '110',
    '이비인후과': '111',
    '이비인후과의학과': '111',
    '피부과': '112',
    '피부과의학과': '112',
    '비뇨의학과': '113',
    '비뇨기과': '113',
    '정신건강의학과': '114',
    '정신과': '114',
    '재활의학과': '115',
    '영상의학과': '116',
    '방사선과': '116',
    '병리과': '117',
    '병리과의학과': '117',
    '진단검사의학과': '118',
    '임상병리과': '118',
    '가정의학과': '119',
    '응급의학과': '120',
    '응급의학과의학과': '120',
}


def normalize_region(region_str: str) -> Optional[str]:
    """
    지역명을 정규화하고 지역 코드로 변환
    
    Args:
        region_str: 원본 지역명 (예: '서울 강남구', '서울시 강남구', '강남구')
    
    Returns:
        지역 코드 (예: '11010') 또는 None
    """
    if not region_str:
        return None
    
    # 공백 제거 및 정규화
    region_str = region_str.strip()
    
    # '시', '도', '구', '군' 등의 불필요한 문자 제거 후 매핑
    normalized = region_str.replace('시', '').replace('도', '').replace('특별시', '').replace('광역시', '')
    
    # 직접 매핑 시도
    if region_str in REGION_MAPPING:
        return REGION_MAPPING[region_str]
    
    if normalized in REGION_MAPPING:
        return REGION_MAPPING[normalized]
    
    # 부분 매칭 시도 (예: '강남구' → '서울 강남구')
    for key, code in REGION_MAPPING.items():
        if region_str in key or key in region_str:
            return code
    
    # 정규표현식으로 패턴 매칭
    # '서울시 강남구' → '서울 강남구'
    patterns = [
        (r'서울[시]?\s*강남구', '11010'),
        (r'서울[시]?\s*강동구', '11020'),
        (r'서울[시]?\s*강북구', '11030'),
        (r'서울[시]?\s*강서구', '11040'),
        (r'부산[시]?\s*해운대구', '26010'),
        (r'경기[도]?\s*수원시', '41010'),
        (r'경기[도]?\s*성남시', '41020'),
    ]
    
    for pattern, code in patterns:
        if re.search(pattern, region_str):
            return code
    
    return None


def normalize_specialty(specialty_str: str) -> Optional[str]:
    """
    전공명을 정규화하고 전공 코드로 변환
    
    Args:
        specialty_str: 원본 전공명 (예: '내과', '내과의학과')
    
    Returns:
        전공 코드 (예: '101') 또는 None
    """
    if not specialty_str:
        return None
    
    # 공백 제거 및 정규화
    specialty_str = specialty_str.strip()
    
    # 직접 매핑 시도
    if specialty_str in SPECIALTY_MAPPING:
        return SPECIALTY_MAPPING[specialty_str]
    
    # '의학과' 제거 후 매핑 시도
    normalized = specialty_str.replace('의학과', '').strip()
    if normalized in SPECIALTY_MAPPING:
        return SPECIALTY_MAPPING[normalized]
    
    # 부분 매칭 시도
    for key, code in SPECIALTY_MAPPING.items():
        if specialty_str in key or key in specialty_str:
            return code
    
    return None


def parse_date(date_str: str) -> Optional[datetime]:
    """
    날짜 문자열을 datetime 객체로 변환
    
    Args:
        date_str: 날짜 문자열 (예: '2025-02-18', '2025.02.18', '2025/02/18')
    
    Returns:
        datetime 객체 또는 None
    """
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # 다양한 날짜 형식 지원
    date_formats = [
        '%Y-%m-%d',
        '%Y.%m.%d',
        '%Y/%m/%d',
        '%Y-%m-%d %H:%M:%S',
        '%Y.%m.%d %H:%M:%S',
        '%Y/%m/%d %H:%M:%S',
        '%Y년 %m월 %d일',
        '%m/%d/%Y',
    ]
    
    for fmt in date_formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None


def clean_data(raw_data: Dict) -> Dict:
    """
    크롤링한 원본 데이터를 정제하고 코드로 변환
    
    Args:
        raw_data: 원본 데이터 딕셔너리
            {
                'title': '공고 제목',
                'hospital_name': '병원명',
                'specialty': '전공명',
                'region': '지역명',
                'register_date': '등록일 문자열',
                'deadline_date': '마감일 문자열',
                'source_id': '원본 사이트 ID',
                'source_url': '원본 URL',
            }
    
    Returns:
        정제된 데이터 딕셔너리
            {
                'title': '공고 제목',
                'hospital_name': '병원명',
                'specialty_code': '101',
                'specialty_raw': '내과',
                'region_code': '11010',
                'region_raw': '서울 강남구',
                'register_date': datetime 객체,
                'deadline_date': datetime 객체,
                'source': 'medigate',
                'source_id': '원본 사이트 ID',
                'source_url': '원본 URL',
            }
    """
    cleaned = {
        'title': raw_data.get('title', '').strip() if raw_data.get('title') else '',
        'hospital_name': raw_data.get('hospital_name', '').strip() if raw_data.get('hospital_name') else '',
        'source': raw_data.get('source', 'medigate'),
        'source_id': raw_data.get('source_id'),
        'source_url': raw_data.get('source_url'),
    }
    
    # 전공 코드화
    specialty_raw = raw_data.get('specialty', '')
    cleaned['specialty_raw'] = specialty_raw.strip() if specialty_raw else None
    cleaned['specialty_code'] = normalize_specialty(specialty_raw)
    
    # 지역 코드화
    region_raw = raw_data.get('region', '')
    cleaned['region_raw'] = region_raw.strip() if region_raw else None
    cleaned['region_code'] = normalize_region(region_raw)
    
    # 날짜 파싱
    register_date_str = raw_data.get('register_date', '')
    cleaned['register_date'] = parse_date(register_date_str) if register_date_str else None
    
    deadline_date_str = raw_data.get('deadline_date', '')
    cleaned['deadline_date'] = parse_date(deadline_date_str) if deadline_date_str else None
    
    return cleaned


# 사용 예시
if __name__ == '__main__':
    # 테스트 데이터
    test_data = {
        'title': '내과 전문의 모집',
        'hospital_name': '강남병원',
        'specialty': '내과',
        'region': '서울 강남구',
        'register_date': '2025-02-18',
        'deadline_date': '2025-03-18',
        'source_id': 'MG12345',
        'source_url': 'https://new.medigate.net/recruit/12345',
    }
    
    cleaned = clean_data(test_data)
    print("정제된 데이터:")
    for key, value in cleaned.items():
        print(f"  {key}: {value}")
```

---

## 4. 다음 단계

### ✅ Phase 2 완료: 모든 Selector 확인 완료

**완료된 작업:**
- ✅ 모든 데이터 필드의 CSS Selector 확인 완료
- ✅ 4개 열 구조 분석 완료
- ✅ 순서 기반 파싱 로직 정의 완료
- ✅ 테스트 크롤링 스크립트 작성 완료 (`test_crawl.py`)

### 📝 test_crawl.py 사용 방법

**파일 위치:** 프로젝트 루트 디렉토리

**실행 방법:**
```bash
python test_crawl.py
```

**기능:**
- 로그인 처리 (bassdoctor / !1q2w3e4r5t)
- 첫 페이지의 공고 10개 추출
- 각 항목이 정확하게 매칭되는지 콘솔에 출력
- 결과를 `test_crawl_results.json` 파일로 저장

**출력 예시:**
```
[공고 1/10]
  ✅ 병원명: 명지병원 (종합병원)
  ✅ 제목: 정형외과 임상강사 모집
  ✅ 전공: 정형외과
  ✅ 고용 형태: 전임의
  ✅ 지역: 경기 고양시 덕양구
  ✅ 마감일: D-10
  ✅ 시작일: 02/11 시작
  ✅ 공고 ID: 12345
```

### ✅ 실제 페이지 구조 확인 완료

**확인된 페이지 구조:**
- URL: `https://www.medigate.net/recruit`
- 페이지 타입: React 기반 동적 페이지 (CSR)
- 총 공고 수: 약 5,057건
- 레이아웃: 카드/행 형식의 리스트
- 각 공고 아이템 구조:
  - 왼쪽: 병원명 + 병원 타입
  - 중앙: 제목/설명 + 전공 태그들
  - 오른쪽: 고용 형태 + 지역 + 마감일 + 시작일 + 온라인 지원 버튼

### 실제 CSS Selector 확인 방법

**현재 상태:** 페이지 구조는 확인했으나, 정확한 CSS Selector는 개발자 도구에서 확인 필요

**확인 절차:**
1. 브라우저에서 `https://www.medigate.net/recruit` 페이지 접속 (로그인 필요)
2. 개발자 도구(F12) 열기
3. Elements 탭에서 각 데이터 요소 선택:
   - 병원명이 있는 요소 선택 → 우클릭 → Copy → Copy selector
   - 제목이 있는 요소 선택 → 우클릭 → Copy → Copy selector
   - 전공 태그 선택 → 우클릭 → Copy → Copy selector
   - 지역 선택 → 우클릭 → Copy → Copy selector
   - 마감일 선택 → 우클릭 → Copy → Copy selector
4. Console에서 테스트:
   ```javascript
   // 예시
   document.querySelector('복사한선택자')
   ```
5. 위의 CSS Selector 예시 부분을 실제 확인한 값으로 교체

**React DevTools 사용 (권장):**
- React DevTools 확장 프로그램 설치
- Components 탭에서 컴포넌트 구조 확인
- 각 컴포넌트의 props와 state 확인 가능

### 크롤링 구현 시 고려사항

1. **로그인 처리**
   - 로그인 필드: `input[name='usrIdT']`, `input[name='usrPasswdT']`
   - 로그인 버튼: `button.button.type1[onclick*='checkLoginForm']`
   - 로그인 후 세션 쿠키 유지 필요
   - Selenium 사용 시 세션 자동 유지됨

2. **React 동적 렌더링 대응**
   - 페이지 로드 후 충분한 대기 시간 필요 (최소 5초)
   - `WebDriverWait`와 `expected_conditions` 사용 권장
   - 요소가 나타날 때까지 명시적 대기

3. **페이지네이션/스크롤 처리**
   - 총 5,057건의 공고가 있으므로 페이지네이션 또는 무한 스크롤 확인 필요
   - 다음 페이지 버튼 클릭 또는 스크롤 다운 처리
   - `driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")` 사용 가능

4. **데이터 추출**
   - 각 공고 아이템을 순회하며 데이터 추출
   - 전공은 여러 개의 태그로 표시되므로 모두 수집
   - 날짜 형식 파싱: "~03/31" → 마감일, "(02/12 시작)" → 시작일
   - 공고 URL에서 공고 ID 추출 (정규표현식 사용)

5. **에러 처리**
   - 네트워크 오류: 재시도 로직 구현
   - 파싱 오류: try-except로 개별 아이템 오류 처리
   - 로그인 실패: 재로그인 시도
   - React 렌더링 실패: 대기 시간 증가 후 재시도

6. **중복 방지**
   - `source_id`를 활용하여 이미 수집한 공고는 제외
   - DB에 저장 전 중복 체크 (UPSERT 사용)

7. **데이터 검증**
   - 필수 필드(병원명, 제목) 누락 시 로그 기록 및 스킵
   - 날짜 형식 검증 및 파싱
   - 지역/전공 코드 매핑 실패 시 원본 데이터 보존

8. **속도 제한**
   - 요청 간 적절한 딜레이 추가 (1-2초)
   - 서버 부하 방지를 위한 Rate Limiting
   - User-Agent 설정으로 봇 차단 방지

9. **상세 페이지 크롤링 (선택사항)**
   - 리스트에서 기본 정보 추출
   - 필요시 각 공고의 상세 페이지 접속하여 추가 정보 추출
   - 상세 페이지 URL은 리스트에서 추출 가능

### 데이터베이스 초기화
```python
from sqlalchemy import create_engine
from models import Base, RegionCode, SpecialtyCode

# PostgreSQL 연결
engine = create_engine('postgresql://user:password@localhost:5432/dbname')

# 테이블 생성
Base.metadata.create_all(engine)

# 초기 데이터 삽입 (위의 SQL 참고)
```

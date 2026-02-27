# -*- coding: utf-8 -*-
"""
메디게이트 구인 공고 크롤러 - Phase 3 테스트
대상: https://www.medigate.net/recruit
전략: 각 공고 행의 자식 요소 순서(Index) 기반 추출
"""

import sys
import io
import time
import json
import re
from datetime import datetime

# Windows cp949 환경에서 UTF-8 출력 강제 설정
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

LOGIN_ID = "bassdoctor"
LOGIN_PW = "!q2w3e4r5t"
BASE_URL = "https://new.medigate.net"
RECRUIT_URL = "https://new.medigate.net/recruit/list"
TARGET_COUNT = 10


def build_unique_key(hospital_name: str, region: str, start_date_str: str) -> str:
    """
    중복 판단용 복합 고유 키 생성.
    기준: 병원명 + 지역 + 시작 연월(YYYY-MM)
    - 제목(title)은 중복 판단에서 완전히 제외
    - 달이 바뀌면 새 구인 수요로 간주하여 다른 키로 처리
    """
    # 시작일 "(MM/DD 시작)" 에서 MM 추출 → 올해 YYYY-MM 구성
    year_month = datetime.now().strftime("%Y-%m")   # 기본값: 크롤링 당월
    if start_date_str:
        m = re.search(r'\((\d{2})/\d{2}', start_date_str)
        if m:
            month = m.group(1)
            year = datetime.now().strftime("%Y")
            year_month = f"{year}-{month}"
    return f"{hospital_name}||{region}||{year_month}"


def get_driver():
    """Chrome WebDriver 초기화"""
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def login(driver):
    """메디게이트 로그인 (new.medigate.net 기준)"""
    print("▶ 메인 페이지 이동 중...")
    driver.get(BASE_URL)
    time.sleep(3)

    wait = WebDriverWait(driver, 20)

    # ID 입력 - 여러 셀렉터 시도
    id_selectors = [
        "input[name='usrIdT']",
        "input[type='text'][name*='id']",
        "input[placeholder*='아이디']",
        "input[placeholder*='ID']",
        "#usrIdT",
    ]
    id_input = None
    for sel in id_selectors:
        try:
            id_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
            print(f"▶ ID 입력창 발견: {sel}")
            break
        except Exception:
            continue

    if not id_input:
        # 페이지 소스를 파일로 저장해서 구조 확인
        with open("C:/medigate_dev/debug_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        raise RuntimeError(f"ID 입력창을 찾을 수 없음. 현재 URL: {driver.current_url}\n디버그 파일: C:/medigate_dev/debug_page.html")

    id_input.clear()
    id_input.send_keys(LOGIN_ID)

    # PW 입력 - 여러 셀렉터 시도
    pw_selectors = [
        "input[name='usrPasswdT']",
        "input[type='password']",
        "input[placeholder*='비밀번호']",
        "#usrPasswdT",
    ]
    pw_input = None
    for sel in pw_selectors:
        try:
            pw_input = driver.find_element(By.CSS_SELECTOR, sel)
            print(f"▶ PW 입력창 발견: {sel}")
            break
        except Exception:
            continue

    if not pw_input:
        raise RuntimeError("비밀번호 입력창을 찾을 수 없음")

    pw_input.clear()
    pw_input.send_keys(LOGIN_PW)

    # 로그인 버튼 - 여러 셀렉터 시도
    btn_selectors = [
        "button[onclick*='checkLoginForm']",
        "button[type='submit']",
        "input[type='submit']",
        "button.login-btn",
        "button:contains('로그인')",
    ]
    login_btn = None
    for sel in btn_selectors:
        try:
            login_btn = driver.find_element(By.CSS_SELECTOR, sel)
            print(f"▶ 로그인 버튼 발견: {sel}")
            break
        except Exception:
            continue

    if not login_btn:
        # Enter 키로 폼 제출 시도
        from selenium.webdriver.common.keys import Keys
        pw_input.send_keys(Keys.RETURN)
        print("▶ Enter 키로 로그인 시도...")
    else:
        login_btn.click()
        print("▶ 로그인 버튼 클릭 완료")

    print("▶ 로그인 세션 대기 중...")
    time.sleep(5)
    print(f"▶ 현재 URL: {driver.current_url}")


def parse_items_from_source(page_source):
    """
    BeautifulSoup으로 공고 행 파싱
    children[0]=1열(병원), [1]=2열(제목), [2]=3열(고용), [3]=4열(날짜)
    """
    soup = BeautifulSoup(page_source, "html.parser")
    results = []
    title_spans = soup.select("span.my-80pqzf")
    if not title_spans:
        print("  ⚠ span.my-80pqzf 요소를 찾을 수 없습니다.")
        return results

    # 중복 판단: 병원명 + 지역 + 등록월(YYYY-MM) 복합 키
    # 제목(title)은 중복 판단 기준에서 완전히 제외
    seen_keys = set()

    for title_span in title_spans:
        title_text = title_span.get_text(strip=True)
        if not title_text:
            continue

        col2 = title_span.find_parent("button")
        if not col2:
            continue
        row = col2.parent
        children = [c for c in row.children if hasattr(c, "name") and c.name]
        if len(children) < 4:
            continue

        col1 = children[0]
        col3 = children[2]
        col4 = children[3]

        # 1열: 병원명, 병원타입
        hospital_name_tag = col1.select_one("span.my-10e3t97")
        hospital_type_tag = col1.select_one("span.my-1cqarh6")
        hospital_name = hospital_name_tag.get_text(strip=True) if hospital_name_tag else ""
        hospital_type = hospital_type_tag.get_text(strip=True) if hospital_type_tag else ""

        # 2열: 제목, 전공
        title = title_text
        specialty_tags = col2.select("span.my-1n83qxm")
        specialties = [t.get_text(strip=True) for t in specialty_tags if t.get_text(strip=True)]

        # 공고 URL
        source_url = ""
        source_id = ""
        parent_a = col2.find_parent("a")
        if parent_a and parent_a.get("href"):
            href = parent_a["href"]
            source_url = href if href.startswith("http") else BASE_URL + href
            m = re.search(r"/recruit/(\d+)", source_url)
            if m:
                source_id = m.group(1)

        # 3열: 고용형태, 지역
        employment_tag = col3.select_one("span.my-10e3t97")
        location_tag = col3.select_one("span.my-1cqarh6")
        employment_type = employment_tag.get_text(strip=True) if employment_tag else ""
        location = location_tag.get_text(strip=True) if location_tag else ""

        # 4열: 마감일, 시작일
        col4_children = [c for c in col4.children if hasattr(c, "name") and c.name]
        deadline = col4_children[0].get_text(strip=True) if len(col4_children) > 0 else ""
        start_date = col4_children[1].get_text(strip=True) if len(col4_children) > 1 else ""

        # ── 복합 고유 키 생성 및 중복 체크 ─────────────────────────
        unique_key = build_unique_key(hospital_name, location, start_date)
        if unique_key in seen_keys:
            print(f"  [SKIP 중복] {unique_key}")
            continue
        seen_keys.add(unique_key)

        # register_date: 시작일에서 추출한 YYYY-MM (DB 저장용)
        register_date = unique_key.split("||")[2]   # "YYYY-MM"

        results.append({
            "병원명": hospital_name,
            "병원타입": hospital_type,
            "제목": title,
            "전공": specialties,
            "고용형태": employment_type,
            "지역": location,
            "마감일": deadline,
            "시작일": start_date,
            "register_date": register_date,
            "unique_key": unique_key,
            "공고ID": source_id,
            "URL": source_url,
        })
        if len(results) >= TARGET_COUNT:
            break

    return results


def parse_with_selenium(driver, existing):
    """셀레니엄 직접 파싱 (fallback)"""
    # 기존 결과의 unique_key 기준으로 중복 판단 (제목 제외)
    seen_keys = {r["unique_key"] for r in existing}
    results = list(existing)
    title_elems = driver.find_elements(By.CSS_SELECTOR, "span.my-80pqzf")

    for title_elem in title_elems:
        if len(results) >= TARGET_COUNT:
            break
        title = title_elem.text.strip()
        if not title:
            continue
        try:
            col2 = title_elem.find_element(By.XPATH, "./ancestor::button[1]")
            row = col2.find_element(By.XPATH, "..")
            children = row.find_elements(By.XPATH, "./*")
            if len(children) < 4:
                continue
            col1 = children[0]
            col3 = children[2]
            col4 = children[3]

            def safe_text(el, sel):
                try:
                    return el.find_element(By.CSS_SELECTOR, sel).text.strip()
                except Exception:
                    return ""

            hospital_name = safe_text(col1, "span.my-10e3t97")
            hospital_type = safe_text(col1, "span.my-1cqarh6")
            spec_tags = col2.find_elements(By.CSS_SELECTOR, "span.my-1n83qxm")
            specialties = [t.text.strip() for t in spec_tags if t.text.strip()]
            employment_type = safe_text(col3, "span.my-10e3t97")
            location = safe_text(col3, "span.my-1cqarh6")
            col4_ch = col4.find_elements(By.XPATH, "./*")
            deadline = col4_ch[0].text.strip() if len(col4_ch) > 0 else ""
            start_date = col4_ch[1].text.strip() if len(col4_ch) > 1 else ""

            # ── 복합 고유 키 중복 체크 (제목 제외) ──────────────────
            unique_key = build_unique_key(hospital_name, location, start_date)
            if unique_key in seen_keys:
                print(f"  [SKIP 중복] {unique_key}")
                continue
            seen_keys.add(unique_key)

            register_date = unique_key.split("||")[2]

            source_url = ""
            source_id = ""
            try:
                a_elem = col2.find_element(By.XPATH, "ancestor::a[1]")
                href = a_elem.get_attribute("href") or ""
                source_url = href
                m = re.search(r"/recruit/(\d+)", href)
                if m:
                    source_id = m.group(1)
            except Exception:
                pass

            results.append({
                "병원명": hospital_name,
                "병원타입": hospital_type,
                "제목": title,
                "전공": specialties,
                "고용형태": employment_type,
                "지역": location,
                "마감일": deadline,
                "시작일": start_date,
                "register_date": register_date,
                "unique_key": unique_key,
                "공고ID": source_id,
                "URL": source_url,
            })
        except Exception as e:
            print(f"  ⚠ Selenium fallback 파싱 오류: {e}")
            continue

    return results


def crawl_first_page():
    """첫 페이지 공고 10개 크롤링"""
    driver = get_driver()
    results = []
    try:
        login(driver)
        print(f"▶ 구인 공고 페이지 이동: {RECRUIT_URL}")
        driver.get(RECRUIT_URL)
        print("▶ 페이지 렌더링 대기 중...")
        wait = WebDriverWait(driver, 20)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "span.my-80pqzf")))
        time.sleep(2)
        print("▶ BeautifulSoup으로 공고 파싱...")
        results = parse_items_from_source(driver.page_source)
        print(f"  → BeautifulSoup 결과: {len(results)}개")
        if len(results) < TARGET_COUNT:
            print("▶ Selenium fallback 파싱...")
            results = parse_with_selenium(driver, results)
            print(f"  → Selenium 결과: {len(results)}개")
    except Exception as e:
        print(f"  ✗ 크롤링 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()
    return results



def print_results(results):
    """결과 터미널 출력"""
    print("\n" + "=" * 60)
    print(f"  총 {len(results)}개 공고 파싱 완료")
    print("=" * 60)
    for i, r in enumerate(results, 1):
        print(f"\n[공고 {i}/{len(results)}]")
        print(f"  ✅ 병원명   : {r['병원명']} ({r['병원타입']})")
        print(f"  ✅ 제목     : {r['제목']}")
        print(f"  ✅ 전공     : {', '.join(r['전공']) if r['전공'] else '-'}")
        print(f"  ✅ 고용형태 : {r['고용형태']}")
        print(f"  ✅ 지역     : {r['지역']}")
        print(f"  ✅ 마감일   : {r['마감일']}")
        print(f"  ✅ 시작일   : {r['시작일']}")
        print(f"  ✅ 공고ID   : {r['공고ID'] if r['공고ID'] else '-'}")
        print(f"  🔑 고유키   : {r['unique_key']}")


if __name__ == "__main__":
    print("=" * 60)
    print("  메디게이트 구인 공고 크롤러 - Phase 3 테스트")
    print("=" * 60)
    data = crawl_first_page()
    print_results(data)
    out_path = "C:/medigate_dev/test_crawl_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n💾 결과 저장: {out_path}")

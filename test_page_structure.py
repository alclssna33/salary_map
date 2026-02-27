#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
구조 탐지 테스트 v2
- new.medigate.net/recruit/list 접근 → 로그인 리다이렉트 → 로그인 완료 후 파싱
"""
import time
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

RECRUIT_URL = "https://new.medigate.net/recruit/list"
USER_ID     = "bassdoctor"
USER_PW     = "!q2w3e4r5t"

def setup_driver():
    options = Options()
    # 테스트용: 창 표시 (문제 확인용)
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    return webdriver.Chrome(options=options)

print("=" * 50)
print("구조 탐지 테스트 v2")
print("=" * 50)

print("\n[1] Chrome 시작...")
try:
    driver = setup_driver()
except Exception as e:
    print(f"Chrome 오류: {e}")
    sys.exit(1)

# ── Step 1: 목표 URL로 접근 (리다이렉트 트리거)
print(f"\n[2] 목표 URL 접근 (로그인 리다이렉트 유도): {RECRUIT_URL}")
driver.get(RECRUIT_URL)
time.sleep(4)
print(f"    현재 URL: {driver.current_url}")
print(f"    페이지 제목: {driver.title}")

# ── Step 2: 로그인 페이지 확인 & 로그인 처리
wait = WebDriverWait(driver, 15)
try:
    print("\n[3] 로그인 필드 탐색...")
    id_field = wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "input[name='usrIdT']")
    ))
    print(f"    아이디 필드 발견 at: {driver.current_url}")

    id_field.clear()
    id_field.send_keys(USER_ID)
    time.sleep(0.5)

    pw_field = driver.find_element(By.CSS_SELECTOR, "input[name='usrPasswdT']")
    pw_field.clear()
    pw_field.send_keys(USER_PW)
    time.sleep(0.5)

    # JavaScript로 직접 로그인 함수 호출 (가장 안정적)
    print("    JavaScript로 로그인 실행...")
    driver.execute_script("checkLoginForm();")

    # 리다이렉트 완료 대기
    print("    리다이렉트 대기 중...")
    time.sleep(8)

    print(f"\n[4] 로그인 후 상태:")
    print(f"    현재 URL: {driver.current_url}")
    print(f"    페이지 제목: {driver.title}")

    # 로그인 성공 여부 확인
    src = driver.page_source
    if 'new.medigate.net' in driver.current_url:
        print("    ✓ 로그인 성공! new.medigate.net에 접근됨")
    elif '로그아웃' in src or 'logout' in src.lower():
        print("    ✓ 로그인 성공! (로그아웃 버튼 감지)")
    elif 'usrIdT' in src:
        print("    ✗ 로그인 실패 - 아직 로그인 페이지에 있음")
        print("      → 비밀번호가 틀렸거나 계정이 잠긴 경우")
    else:
        print(f"    ? 상태 불명확")

except Exception as e:
    print(f"    오류: {e}")

# ── Step 3: HTML 저장 & 구조 분석
with open('new_site_page.html', 'w', encoding='utf-8') as f:
    f.write(driver.page_source)
print("\n[5] new_site_page.html 저장 완료")

soup = BeautifulSoup(driver.page_source, 'html.parser')
print("\n=== 페이지 구조 ===")
print(f"table 수: {len(soup.find_all('table'))}")
print(f"ul 수:    {len(soup.find_all('ul'))}")
print(f"li 수:    {len(soup.find_all('li'))}")
print(f"a 링크:   {len(soup.find_all('a'))}")

print("\n클래스명이 있는 div (list/board/recruit 관련):")
found = 0
for div in soup.find_all('div', class_=True):
    cls = ' '.join(div.get('class', []))
    if any(k in cls.lower() for k in ['list', 'board', 'recruit', 'post', 'item', 'wrap', 'content']):
        print(f"  div.{cls}")
        found += 1
    if found >= 20:
        break

print("\nli 항목 샘플:")
for li in soup.find_all('li')[:5]:
    print(f"  li class={li.get('class',[])} text={li.get_text(strip=True)[:60]!r}")

print("\ntable 목록:")
for i, t in enumerate(soup.find_all('table')):
    cls = ' '.join(t.get('class', []))
    rows = t.find_all('tr')
    print(f"  테이블{i+1}: class={cls!r}, {len(rows)}행")
    for row in rows[:2]:
        print(f"    tr: {row.get_text(strip=True)[:80]!r}")

driver.quit()
print("\n완료!")

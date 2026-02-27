#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""페이지네이션 방식 테스트"""
import re, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

RECRUIT_URL = "https://new.medigate.net/recruit/list"
USER_ID     = "bassdoctor"
USER_PW     = "!q2w3e4r5t"

options = Options()
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--headless=new')
options.add_argument('--window-size=1920,1080')
options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

driver = webdriver.Chrome(options=options)

# 로그인
print("로그인 중...")
driver.get(RECRUIT_URL)
time.sleep(4)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
wait = WebDriverWait(driver, 15)
wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='usrIdT']"))).send_keys(USER_ID)
driver.find_element(By.CSS_SELECTOR, "input[name='usrPasswdT']").send_keys(USER_PW)
driver.execute_script("checkLoginForm();")
time.sleep(5)
print(f"현재 URL: {driver.current_url}")

def count_posts(soup):
    links = [a for a in soup.find_all('a') if re.match(r'^/recruit/\d+$', a.get('href',''))]
    return len(links), [a.get('href') for a in links[:3]]

# 1페이지 확인
print("\n=== 1페이지 (기본) ===")
soup1 = BeautifulSoup(driver.page_source, 'html.parser')
n, hrefs = count_posts(soup1)
print(f"  공고 수: {n}, 샘플 href: {hrefs}")

# 시도 1: ?page=2
print("\n=== ?page=2 테스트 ===")
driver.get(f"{RECRUIT_URL}?page=2")
time.sleep(4)
print(f"  현재 URL: {driver.current_url}")
soup2 = BeautifulSoup(driver.page_source, 'html.parser')
n2, hrefs2 = count_posts(soup2)
print(f"  공고 수: {n2}, 샘플 href: {hrefs2}")
same = set(hrefs) & set(hrefs2)
print(f"  1페이지와 중복: {len(same)}개 {'(같은 페이지!)' if same else '(다른 페이지!)'}")

# 시도 2: ?pageNo=2
print("\n=== ?pageNo=2 테스트 ===")
driver.get(f"{RECRUIT_URL}?pageNo=2")
time.sleep(4)
soup3 = BeautifulSoup(driver.page_source, 'html.parser')
n3, hrefs3 = count_posts(soup3)
print(f"  공고 수: {n3}, 샘플 href: {hrefs3}")
same3 = set(hrefs) & set(hrefs3)
print(f"  1페이지와 중복: {len(same3)}개 {'(같은 페이지!)' if same3 else '(다른 페이지!)'}")

# 페이지네이션 버튼 찾기
print("\n=== 페이지네이션 버튼 탐색 ===")
all_btns = soup1.find_all(['button', 'a'])
for b in all_btns:
    txt = b.get_text(strip=True)
    href = b.get('href', b.get('data-page', ''))
    cls = ' '.join(b.get('class', []))
    if txt in ['다음', '>', '>>', '이전', '<', '<<', '2', '3'] or 'next' in cls.lower() or 'prev' in cls.lower():
        print(f"  <{b.name}> text={txt!r} href={href!r} class={cls[:60]!r}")

driver.quit()
print("\n완료!")

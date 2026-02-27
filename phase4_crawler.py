#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 4: 메디게이트 전체 공고 수집 및 DB 저장 (급여 통합)
- 대상: new.medigate.net/recruit/list
- 페이지네이션: ?pageNo=N
- 중복 제거: 병원명 + 지역(시도) + 등록월 (unique_key)
- DB: medigate / recruit_posts + recruit_post_specialties
- 신규 공고만 상세 페이지 방문 → 급여 파싱 → 즉시 저장
- 딜레이: 목록 페이지 1~2초, 상세 페이지 1.5~2.5초
- 진행 알림: 100건마다 출력

실행 예시
---------
  # DB 현황만 확인 (크롤링 없이)
  python phase4_crawler.py --info

  # 날짜 범위 지정
  python phase4_crawler.py --from 2026-02-19 --to 2026-02-23

  # 시작일만 지정 (해당 날짜 이후 전부)
  python phase4_crawler.py --from 2026-02-19

  # 전체 수집 (날짜 제한 없음)
  python phase4_crawler.py
"""

import argparse
import time
import random
import re
import sys
import os
from datetime import datetime

# ──────────────────────────────────────────────────────────
# 로그 파일 설정 (stdout + 파일 동시 출력)
# ──────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = open(os.path.join(_SCRIPT_DIR, 'crawl_log.txt'), 'w', encoding='utf-8', buffering=1)

def log(msg):
    """stdout과 로그 파일에 동시 출력"""
    try:
        sys.stdout.buffer.write((str(msg) + '\n').encode('utf-8'))
        sys.stdout.buffer.flush()
    except Exception:
        try:
            sys.stdout.write(str(msg) + '\n')
            sys.stdout.flush()
        except Exception:
            pass
    LOG_FILE.write(str(msg) + '\n')
    LOG_FILE.flush()


import psycopg2
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

from salary_calculator import parse_salary


# ============================================================
# 설정
# ============================================================
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'dbname': 'medigate',
    'user': 'postgres',
    'password': 'postgres',
}

LOGIN_TRIGGER_URL = "https://new.medigate.net/recruit/list"
BASE_URL          = "https://new.medigate.net"
RECRUIT_URL       = f"{BASE_URL}/recruit/list"
USER_ID           = "bassdoctor"
USER_PW           = "!q2w3e4r5t"

DELAY_MIN         = 1.0    # 목록 페이지 간 최소 딜레이(초)
DELAY_MAX         = 2.0    # 목록 페이지 간 최대 딜레이(초)
DETAIL_DELAY_MIN  = 1.5    # 상세 페이지 최소 딜레이(초)
DETAIL_DELAY_MAX  = 2.5    # 상세 페이지 최대 딜레이(초)
DETAIL_RETRY      = 2      # 상세 페이지 로드 실패 시 재시도 횟수
PROGRESS_INTERVAL = 100    # N건마다 진행상황 출력
PAGE_LOAD_WAIT    = 15     # JS 렌더링 최대 대기(초)
POSTS_PER_PAGE    = 48     # 페이지당 공고 수 (실측)
CRAWL_YEAR        = 2026   # 등록일 연도 기준 (현재 년도)
CURRENT_MONTH     = 2      # 현재 월 (2월 = 2025년 3~12월 / 2026년 1~2월)


# ============================================================
# 인자 파싱
# ============================================================
def parse_args():
    parser = argparse.ArgumentParser(
        description='메디게이트 구인 공고 크롤러',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python phase4_crawler.py --info                          # DB 현황만 확인
  python phase4_crawler.py --from 2026-02-19 --to 2026-02-23
  python phase4_crawler.py --from 2026-02-19              # 해당일 이후 전부
  python phase4_crawler.py                                 # 전체 수집
        """
    )
    parser.add_argument(
        '--from', dest='date_from', type=str, default=None,
        metavar='YYYY-MM-DD',
        help='수집 시작일 (이 날짜 이후 공고만 수집)',
    )
    parser.add_argument(
        '--to', dest='date_to', type=str, default=None,
        metavar='YYYY-MM-DD',
        help='수집 종료일 (이 날짜 이전 공고만 수집)',
    )
    parser.add_argument(
        '--info', action='store_true',
        help='DB 현황만 확인하고 종료 (크롤링 없음)',
    )
    return parser.parse_args()


def validate_date(s):
    """YYYY-MM-DD 형식 검증 후 반환. 잘못된 형식이면 종료."""
    if s is None:
        return None
    try:
        datetime.strptime(s, '%Y-%m-%d')
        return s
    except ValueError:
        log(f"  [오류] 날짜 형식이 잘못되었습니다: '{s}'  (올바른 형식: YYYY-MM-DD)")
        sys.exit(1)


# ============================================================
# DB 현황 출력
# ============================================================
def show_db_summary(conn):
    """DB에 저장된 데이터 현황을 출력"""
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*)                                    AS total,
            MAX(register_date)                          AS latest,
            MIN(register_date)                          AS oldest,
            COUNT(CASE WHEN salary_fetched = TRUE THEN 1 END) AS with_salary
        FROM recruit_posts
        WHERE source = 'medigate'
          AND register_date IS NOT NULL
          AND register_date <> ''
    """)
    row = cur.fetchone()

    # 최근 5개월 월별 건수
    cur.execute("""
        SELECT LEFT(register_date, 7) AS ym, COUNT(*) AS cnt
        FROM   recruit_posts
        WHERE  source = 'medigate'
          AND  register_date IS NOT NULL AND register_date <> ''
        GROUP  BY ym
        ORDER  BY ym DESC
        LIMIT  5
    """)
    monthly = cur.fetchall()
    cur.close()

    log("")
    log("┌─────────────────────────────────────────────┐")
    log("│            현재 DB 데이터 현황               │")
    log("├─────────────────────────────────────────────┤")
    if row and row[0]:
        total, latest, oldest, with_sal = row
        log(f"│  총 저장 건수   : {total:>6,}건                   │")
        log(f"│  최신 등록일    : {latest}                  │")
        log(f"│  가장 오래된 일 : {oldest}                  │")
        log(f"│  급여 수집 완료 : {with_sal:>6,}건                   │")
        log("├─────────────────────────────────────────────┤")
        log("│  최근 월별 공고 수                           │")
        for ym, cnt in monthly:
            log(f"│    {ym}  :  {cnt:>5,}건                        │")
    else:
        log("│  저장된 데이터 없음                          │")
    log("└─────────────────────────────────────────────┘")
    log("")


# ============================================================
# 브라우저 설정 & 로그인
# ============================================================
def setup_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.page_load_strategy = 'eager'
    options.add_argument('--blink-settings=imagesEnabled=false')
    options.add_argument('--disable-features=NetworkService')
    options.add_argument(
        'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(20)
    return driver


def login(driver):
    """new.medigate.net으로 접근 → 로그인 리다이렉트 → 로그인 완료"""
    log("[LOGIN] 로그인 중...")
    driver.get(LOGIN_TRIGGER_URL)
    time.sleep(4)

    try:
        wait = WebDriverWait(driver, 15)
        id_field = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[name='usrIdT']")
        ))
        id_field.clear()
        id_field.send_keys(USER_ID)
        time.sleep(0.3)

        pw_field = driver.find_element(By.CSS_SELECTOR, "input[name='usrPasswdT']")
        pw_field.clear()
        pw_field.send_keys(USER_PW)
        time.sleep(0.3)

        driver.execute_script("checkLoginForm();")
        time.sleep(6)

        if 'new.medigate.net' in driver.current_url:
            log(f"[OK] 로그인 성공 -> {driver.current_url}")
            return True
        else:
            log(f"[FAIL] 로그인 실패 (현재 URL: {driver.current_url})")
            return False

    except Exception as e:
        log(f"[ERROR] 로그인 오류: {e}")
        return False


# ============================================================
# 페이지 로딩
# ============================================================
def load_page(driver, page_no):
    url = f"{RECRUIT_URL}?sorter=regDate&pageNo={page_no}"
    try:
        driver.get(url)
    except Exception as e:
        log(f"    ⚠ 페이지 {page_no} 로드 시간 초과 발생")
    try:
        WebDriverWait(driver, PAGE_LOAD_WAIT).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except Exception:
        pass
    time.sleep(1.5)


# ============================================================
# 공고 파싱
# ============================================================
def infer_year(month_str):
    try:
        m = int(month_str)
        return CRAWL_YEAR if m <= CURRENT_MONTH else CRAWL_YEAR - 1
    except Exception:
        return CRAWL_YEAR


def parse_register_date(date_raw):
    m = re.search(r'\((\d{1,2})/(\d{1,2})', date_raw)
    if m:
        mo  = m.group(1).zfill(2)
        day = m.group(2).zfill(2)
        yr  = infer_year(mo)
        return f"{yr}-{mo}-{day}"
    return ''


def clean_title(title, specialties):
    for sp in reversed(specialties):
        if title.endswith(sp):
            title = title[: -len(sp)].strip()
    return title.strip()


def extract_posts_from_soup(soup):
    posts = []
    recruit_links = [
        a for a in soup.find_all('a')
        if re.match(r'^/recruit/\d+$', a.get('href', ''))
    ]

    seen_hrefs = set()
    for link in recruit_links:
        href = link.get('href', '')
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        card = link
        for _ in range(8):
            card = card.parent
            if not card or card.name in ['html', 'body', '[document]']:
                card = None
                break
            sibling_count = sum(
                1 for s in card.parent.children
                if getattr(s, 'get', None) and s.get('class') == card.get('class')
            )
            if sibling_count >= 10:
                break

        if not card:
            continue
        try:
            post = parse_card(card, href)
            if post:
                posts.append(post)
        except Exception:
            continue

    return posts


def parse_card(card, href):
    post_id = re.search(r'/recruit/(\d+)', href)
    post_id = post_id.group(1) if post_id else ''
    url     = BASE_URL + href

    w220 = card.select_one('div[class*="w-[220px]"]')
    hospital_name = hospital_type = ''
    if w220:
        parts = [s.get_text(strip=True) for s in w220.find_all(
            ['span', 'p', 'div'], recursive=False
        ) if s.get_text(strip=True)]
        if not parts:
            parts = w220.get_text(separator='/', strip=True).split('/', 1)
        hospital_name = parts[0] if parts else ''
        hospital_type = parts[1] if len(parts) > 1 else ''

    w130 = card.select_one('div[class*="w-[130px]"]')
    employment_type = region = ''
    if w130:
        parts130 = [s.get_text(strip=True) for s in w130.find_all(
            ['span', 'p'], recursive=False
        ) if s.get_text(strip=True)]
        if not parts130:
            parts130 = w130.get_text(separator='/', strip=True).split('/', 1)
        employment_type = parts130[0] if parts130 else ''
        region          = parts130[1] if len(parts130) > 1 else ''

    w120 = card.select_one('div[class*="w-[120px]"]')
    deadline = register_date = ''
    if w120:
        parts120 = [s.get_text(strip=True) for s in w120.find_all(
            ['span', 'p'], recursive=False
        ) if s.get_text(strip=True)]
        if not parts120:
            parts120 = w120.get_text(separator='/', strip=True).split('/', 1)
        deadline_raw  = parts120[0] if parts120 else ''
        date_raw      = parts120[1] if len(parts120) > 1 else ''
        deadline      = deadline_raw
        register_date = parse_register_date(date_raw)

    spec_spans  = card.select('span.my-1n83qxm')
    specialties = [s.get_text(strip=True) for s in spec_spans if s.get_text(strip=True)]

    btn   = card.select_one('button')
    title = btn.get_text(strip=True) if btn else ''
    title = clean_title(title, specialties)

    region_sido = region.split()[0] if region else ''

    if not hospital_name and not title:
        return None

    return {
        'post_id':         post_id,
        'url':             url,
        'title':           title,
        'hospital_name':   hospital_name,
        'hospital_type':   hospital_type,
        'specialty_list':  specialties,
        'region':          region,
        'region_sido':     region_sido,
        'employment_type': employment_type,
        'register_date':   register_date,
        'deadline':        deadline,
    }


# ============================================================
# 페이지 수 계산
# ============================================================
def get_total_pages(soup):
    for pattern in [r'총\s*([\d,]+)\s*건', r'([\d,]+)\s*건']:
        matches = re.findall(pattern, soup.get_text())
        for m in matches:
            try:
                total = int(m.replace(',', ''))
                if total > 100:
                    pages = -(-total // POSTS_PER_PAGE)
                    log(f"    총 {total:,}건 감지 → {POSTS_PER_PAGE}건/페이지 기준 약 {pages}페이지")
                    return pages
            except Exception:
                pass

    max_page = 1
    for btn in soup.find_all('button'):
        try:
            n = int(btn.get_text(strip=True))
            max_page = max(max_page, n)
        except Exception:
            pass

    if max_page > 1:
        return max_page * 10

    return 120


# ============================================================
# 상세 페이지 급여 추출
# ============================================================
def extract_salary_text(driver, url: str):
    for attempt in range(DETAIL_RETRY + 1):
        try:
            driver.get(url)
            WebDriverWait(driver, 12).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(1.2)

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            for row in soup.find_all('div', class_='my-qjvukt'):
                label = row.find('span', class_='my-1daa3uy')
                if label and label.get_text(strip=True) == '급여':
                    val_div = row.find(
                        'div',
                        class_=lambda c: c and 'flex-[1_0_0]' in c
                    )
                    if val_div:
                        return val_div.get_text(separator=' ', strip=True)
            return None

        except Exception as e:
            if attempt < DETAIL_RETRY:
                time.sleep(3)
            else:
                raise


# ============================================================
# DB 처리
# ============================================================
def load_existing_keys(conn):
    cur = conn.cursor()
    cur.execute("SELECT unique_key FROM recruit_posts WHERE source='medigate'")
    keys = {row[0] for row in cur.fetchall()}
    cur.close()
    return keys


def make_unique_key(hospital_name, region_sido, register_date):
    month = ''
    if register_date:
        parts = re.split(r'[-./]', str(register_date).strip())
        if len(parts) >= 2:
            month = f"{parts[0]}-{parts[1].zfill(2)}"
    h = (hospital_name or '').strip()
    r = (region_sido  or '').strip()
    return f"{h}|{r}|{month}"


def save_to_db(conn, post, existing_keys):
    """신규 공고 저장. 신규이면 new_id(int) 반환, 중복/오류이면 None 반환."""
    ukey = make_unique_key(
        post['hospital_name'], post['region_sido'], post['register_date']
    )
    if ukey in existing_keys:
        return None

    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO recruit_posts
                (source, post_id, unique_key, hospital_name, hospital_type,
                 title, employment_type, region, region_sido, deadline,
                 register_date, url, is_active, crawled_at, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s, %s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            'medigate',
            post['post_id']         or '',
            ukey,
            post['hospital_name']   or '',
            post['hospital_type']   or '',
            post['title']           or '',
            post['employment_type'] or '',
            post['region']          or '',
            post['region_sido']     or '',
            post['deadline']        or '',
            post['register_date']   or '',
            post['url']             or '',
            True,
            datetime.now(), datetime.now(), datetime.now(),
        ))
        new_id = cur.fetchone()[0]

        for sp in post.get('specialty_list', []):
            if sp and len(sp) >= 2:
                cur.execute(
                    "INSERT INTO recruit_post_specialties (post_id, specialty) VALUES (%s,%s)",
                    (new_id, sp)
                )

        conn.commit()
        existing_keys.add(ukey)
        return new_id

    except Exception as e:
        conn.rollback()
        log(f"    ⚠ DB 저장 오류: {e}")
        return None
    finally:
        cur.close()


def save_salary(conn, db_id: int, raw_text, parsed: dict):
    """급여 파싱 결과를 DB에 저장. salary_fetched=TRUE 항상 설정."""
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE recruit_posts SET
                salary_raw     = %s,
                salary_type    = %s,
                salary_unit    = %s,
                salary_min     = %s,
                salary_max     = %s,
                salary_net_min = %s,
                salary_net_max = %s,
                salary_fetched = TRUE
            WHERE id = %s
        """, (
            raw_text,
            parsed.get('salary_type'),
            parsed.get('salary_unit'),
            parsed.get('salary_min'),
            parsed.get('salary_max'),
            parsed.get('salary_net_min'),
            parsed.get('salary_net_max'),
            db_id,
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        log(f"    ⚠ 급여 저장 오류 id={db_id}: {e}")
    finally:
        cur.close()


# ============================================================
# 메인
# ============================================================
def main():
    args = parse_args()
    date_from = validate_date(args.date_from)
    date_to   = validate_date(args.date_to)

    log("=" * 62)
    log("  Phase 4: 메디게이트 전체 공고 수집 & DB 저장 (급여 통합)")
    log(f"  시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 62)

    # ── DB 연결 & 현황 출력
    log("\n[1] PostgreSQL 연결...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        existing_keys = load_existing_keys(conn)
        log(f"    기존 저장 건수: {len(existing_keys):,}건")
    except Exception as e:
        log(f"    DB 연결 실패: {e}")
        sys.exit(1)

    # DB 현황 항상 출력
    show_db_summary(conn)

    # --info 옵션이면 여기서 종료
    if args.info:
        conn.close()
        LOG_FILE.close()
        return

    # 수집 날짜 범위 출력
    log("  수집 날짜 범위:")
    log(f"    시작일 : {date_from if date_from else '제한 없음 (전체)'}")
    log(f"    종료일 : {date_to   if date_to   else '제한 없음 (전체)'}")
    log("")

    start_time = datetime.now()

    # ── 브라우저 & 로그인
    log("[2] Chrome 브라우저 시작...")
    driver = setup_driver()

    if not login(driver):
        log("로그인 실패. 종료합니다.")
        driver.quit()
        conn.close()
        sys.exit(1)

    # ── 1페이지 로드 & 총 페이지 수 파악
    log(f"\n[3] 1페이지 로드...")
    load_page(driver, 1)
    soup1 = BeautifulSoup(driver.page_source, 'html.parser')
    last_page = get_total_pages(soup1)

    first_posts = extract_posts_from_soup(soup1)
    log(f"    1페이지 파싱: {len(first_posts)}건")
    if first_posts:
        p = first_posts[0]
        log(f"    샘플: {p['hospital_name']!r} / {p['region']!r} / "
              f"{p['register_date']!r} / 전공={p['specialty_list']}")
    else:
        log("    ⚠ 1페이지에서 공고를 찾지 못했습니다!")
        with open('debug_page.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        log("    debug_page.html 저장 완료")
        driver.quit()
        conn.close()
        sys.exit(1)

    # ── 수집 루프
    log(f"\n[4] 수집 시작! (총 예상 페이지: {last_page})\n"
        f"    목록 딜레이 {DELAY_MIN}~{DELAY_MAX}초 "
        f"/ 상세(급여) 딜레이 {DETAIL_DELAY_MIN}~{DETAIL_DELAY_MAX}초\n")

    total_saved     = 0
    total_skipped   = 0
    total_out_range = 0   # 날짜 범위 밖 스킵
    total_processed = 0
    cnt_salary      = 0
    cnt_nego        = 0
    cnt_no_salary   = 0
    cnt_sal_err     = 0
    consec_empty    = 0
    stop_crawl      = False

    # 날짜 범위 이전 페이지가 연속으로 나오면 종료하기 위한 카운터
    pages_past_range = 0

    for page in range(1, last_page + 1):
        if stop_crawl:
            break

        if page > 1:
            load_page(driver, page)
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        soup  = BeautifulSoup(driver.page_source, 'html.parser')
        posts = extract_posts_from_soup(soup)

        if not posts:
            consec_empty += 1
            if consec_empty >= 3:
                log(f"  → 3페이지 연속 공고 없음 (페이지 {page}). 수집 완료 판단.")
                break
            continue
        else:
            consec_empty = 0

        # ── 이 페이지의 날짜 범위 조기 종료 판단
        # 공고가 모두 date_from 이전이면 더 이상 진행 불필요
        if date_from:
            dates_on_page = [
                p['register_date'] for p in posts
                if p.get('register_date')
            ]
            if dates_on_page and max(dates_on_page) < date_from:
                pages_past_range += 1
                if pages_past_range >= 2:
                    log(f"  → 수집 범위({date_from}) 이전 날짜 페이지 2페이지 연속 감지."
                        f" 종료합니다. (페이지 {page}, 최신일: {max(dates_on_page)})")
                    stop_crawl = True
                    break
            else:
                pages_past_range = 0

        for post in posts:
            reg_date = post.get('register_date', '')

            # ── 날짜 범위 필터
            if date_to and reg_date and reg_date > date_to:
                total_out_range += 1
                continue  # 종료일 이후 → 스킵
            if date_from and reg_date and reg_date < date_from:
                total_out_range += 1
                continue  # 시작일 이전 → 스킵

            total_processed += 1

            new_id = save_to_db(conn, post, existing_keys)

            if new_id is None:
                total_skipped += 1
            else:
                # 신규 — 상세 페이지 방문하여 급여 수집
                total_saved += 1
                raw_text = None
                parsed   = {}
                try:
                    raw_text = extract_salary_text(driver, post['url'])
                    parsed   = parse_salary(raw_text) if raw_text else {}
                except Exception as e:
                    log(f"    ⚠ 급여 수집 오류 (id={new_id}): {e}")
                    cnt_sal_err += 1

                save_salary(conn, new_id, raw_text, parsed)

                if parsed.get('salary_net_min') is not None:
                    cnt_salary += 1
                elif raw_text and parsed.get('salary_type') is None:
                    cnt_nego += 1
                else:
                    cnt_no_salary += 1

                time.sleep(random.uniform(DETAIL_DELAY_MIN, DETAIL_DELAY_MAX))

            if total_processed % PROGRESS_INTERVAL == 0:
                elapsed = max(1, (datetime.now() - start_time).seconds)
                speed   = total_processed / elapsed * 60
                log(
                    f"  [{total_processed:>5}건 처리] "
                    f"신규 {total_saved}건 (급여 {cnt_salary} / 협의 {cnt_nego} / 없음 {cnt_no_salary}) "
                    f"| 중복 {total_skipped}건 | {speed:.0f}건/분"
                )

        if page % 10 == 0 or page == 1:
            log(f"  [페이지 {page}/{last_page}] 이 페이지 {len(posts)}건 | "
                  f"누적 {total_processed}건 (신규 {total_saved} / 중복 {total_skipped} "
                  f"/ 범위외 {total_out_range})")

    # ── 최종 결과
    elapsed_total = max(1, (datetime.now() - start_time).seconds)
    log("\n" + "=" * 62)
    log("  수집 완료!")
    log(f"  날짜 범위    : {date_from or '전체'} ~ {date_to or '전체'}")
    log(f"  총 처리 건수 : {total_processed:,}건  (범위 외 스킵: {total_out_range}건)")
    log(f"  신규 저장    : {total_saved:,}건")
    log(f"    ├ 급여 파싱 성공  : {cnt_salary:,}건")
    log(f"    ├ 협의/미정       : {cnt_nego:,}건")
    log(f"    ├ 급여 행 없음    : {cnt_no_salary:,}건")
    log(f"    └ 급여 수집 오류  : {cnt_sal_err:,}건")
    log(f"  중복 스킵    : {total_skipped:,}건")
    log(f"  소요 시간    : {elapsed_total // 60}분 {elapsed_total % 60}초")
    log(f"  종료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 62)

    driver.quit()
    conn.close()
    LOG_FILE.close()


if __name__ == '__main__':
    main()

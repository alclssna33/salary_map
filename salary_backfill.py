#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
salary_backfill.py — 기존 DB 공고에 급여 데이터 추가
─────────────────────────────────────────────────────
처리 흐름:
  1. recruit_posts 테이블에 급여 컬럼 7개 추가 (없으면)
  2. salary_fetched = FALSE 인 공고만 선택
  3. 각 공고 상세 페이지 방문 → 모집개요 '급여' 행 파싱
  4. salary_calculator.py 로 Net 환산 → DB UPDATE

실행:
  python salary_backfill.py

로그:
  salary_backfill_log.txt (실시간)
"""

import time
import random
import sys
import os
import re
from datetime import datetime

import psycopg2
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

from salary_calculator import parse_salary

# ══════════════════════════════════════════════════════════════
# 설정
# ══════════════════════════════════════════════════════════════
DB_CONFIG = {
    'host': 'localhost', 'port': 5432,
    'dbname': 'medigate', 'user': 'postgres', 'password': 'postgres',
}
LOGIN_URL  = "https://new.medigate.net/recruit/list"
USER_ID    = "bassdoctor"
USER_PW    = "!q2w3e4r5t"

DELAY_MIN  = 1.5   # 페이지 간 최소 딜레이(초)
DELAY_MAX  = 2.5   # 페이지 간 최대 딜레이(초)
PROGRESS_N = 50    # N건마다 진행 출력
MAX_RETRY  = 2     # 페이지 로드 실패 시 재시도 횟수

# ── 로그 설정 ─────────────────────────────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG = open(os.path.join(_DIR, 'salary_backfill_log.txt'), 'w',
            encoding='utf-8', buffering=1)

def log(msg: str):
    try:
        sys.stdout.buffer.write((str(msg) + '\n').encode('utf-8'))
        sys.stdout.buffer.flush()
    except Exception:
        pass
    _LOG.write(str(msg) + '\n')
    _LOG.flush()


# ══════════════════════════════════════════════════════════════
# DB 처리
# ══════════════════════════════════════════════════════════════
SALARY_COLS = [
    ("salary_raw",     "TEXT"),
    ("salary_type",    "VARCHAR(10)"),
    ("salary_unit",    "VARCHAR(10)"),
    ("salary_min",     "INTEGER"),
    ("salary_max",     "INTEGER"),
    ("salary_net_min", "INTEGER"),
    ("salary_net_max", "INTEGER"),
    ("salary_fetched", "BOOLEAN DEFAULT FALSE"),
]

def ensure_columns(conn):
    """급여 관련 컬럼이 없으면 ALTER TABLE 로 추가"""
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'recruit_posts'
    """)
    existing = {r[0] for r in cur.fetchall()}
    cur.close()

    added = []
    for col, dtype in SALARY_COLS:
        if col not in existing:
            cur = conn.cursor()
            cur.execute(f'ALTER TABLE recruit_posts ADD COLUMN "{col}" {dtype}')
            cur.close()
            added.append(col)

    if added:
        conn.commit()
        log(f"  [DB] 컬럼 추가: {', '.join(added)}")
    else:
        log("  [DB] 급여 컬럼 이미 존재")


def fetch_pending(conn):
    """아직 급여 수집을 하지 않은 공고 목록 반환"""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, post_id, url
        FROM   recruit_posts
        WHERE  source = 'medigate'
          AND  post_id <> ''
          AND  (salary_fetched IS NULL OR salary_fetched = FALSE)
        ORDER  BY id
    """)
    rows = cur.fetchall()
    cur.close()
    return rows


def save_salary(conn, db_id: int, raw_text, parsed: dict):
    """급여 파싱 결과를 DB에 저장"""
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
            parsed['salary_type'],
            parsed['salary_unit'],
            parsed['salary_min'],
            parsed['salary_max'],
            parsed['salary_net_min'],
            parsed['salary_net_max'],
            db_id,
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        log(f"  [DB오류] id={db_id}: {e}")
    finally:
        cur.close()


def mark_fetched(conn, db_id: int):
    """급여 정보 없는 공고도 '방문 완료' 표시 (재시도 방지)"""
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE recruit_posts SET salary_fetched = TRUE WHERE id = %s",
            (db_id,)
        )
        conn.commit()
    finally:
        cur.close()


# ══════════════════════════════════════════════════════════════
# 브라우저 / 로그인
# ══════════════════════════════════════════════════════════════
def setup_driver():
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument(
        'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    return webdriver.Chrome(options=opts)


def login(driver) -> bool:
    driver.get(LOGIN_URL)
    time.sleep(4)
    try:
        wait = WebDriverWait(driver, 15)
        id_f = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[name='usrIdT']")
        ))
        id_f.send_keys(USER_ID)
        driver.find_element(By.CSS_SELECTOR, "input[name='usrPasswdT']").send_keys(USER_PW)
        driver.execute_script("checkLoginForm();")
        time.sleep(6)
        return 'new.medigate.net' in driver.current_url
    except Exception as e:
        log(f"  [로그인 오류] {e}")
        return False


# ══════════════════════════════════════════════════════════════
# 상세 페이지에서 급여 텍스트 추출
# ══════════════════════════════════════════════════════════════
def extract_salary_text(driver, url: str) -> str | None:
    """
    공고 상세 페이지 방문 → 모집개요 '급여' 행 텍스트 반환
    급여 행 없으면 None 반환
    """
    for attempt in range(MAX_RETRY + 1):
        try:
            driver.get(url)
            # JS 렌더링 대기
            WebDriverWait(driver, 12).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(1.2)   # React hydration 추가 대기

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # 모집개요 행: div.my-qjvukt
            for row in soup.find_all('div', class_='my-qjvukt'):
                label = row.find('span', class_='my-1daa3uy')
                if label and label.get_text(strip=True) == '급여':
                    val_div = row.find(
                        'div',
                        class_=lambda c: c and 'flex-[1_0_0]' in c
                    )
                    if val_div:
                        return val_div.get_text(separator=' ', strip=True)
            return None   # 급여 행 없음

        except Exception as e:
            if attempt < MAX_RETRY:
                log(f"  [재시도 {attempt+1}/{MAX_RETRY}] {url[:60]}... ({e})")
                time.sleep(3)
            else:
                raise


# ══════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════
def main():
    log("=" * 62)
    log("  급여 Backfill 시작")
    log(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 62)
    start = datetime.now()

    # ── DB 연결 & 컬럼 확인 ─────────────────────────────────
    log("\n[1] PostgreSQL 연결 및 컬럼 확인...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        log(f"  DB 연결 실패: {e}")
        sys.exit(1)

    ensure_columns(conn)

    posts = fetch_pending(conn)
    total = len(posts)
    log(f"  처리 대상: {total:,}건\n")

    if total == 0:
        log("처리할 공고 없음. (모두 salary_fetched=TRUE)")
        conn.close()
        return

    # ── 브라우저 & 로그인 ────────────────────────────────────
    log("[2] Chrome 브라우저 시작 및 로그인...")
    driver = setup_driver()
    if not login(driver):
        log("  [ERROR] 로그인 실패. 종료합니다.")
        driver.quit()
        conn.close()
        sys.exit(1)
    log("  [OK] 로그인 성공\n")

    # ── 수집 루프 ────────────────────────────────────────────
    log(f"[3] 급여 수집 시작 (딜레이 {DELAY_MIN}~{DELAY_MAX}초)\n")

    cnt_total   = 0  # 방문 완료
    cnt_salary  = 0  # 급여 파싱 성공 (Net 환산까지)
    cnt_nego    = 0  # 협의/미정
    cnt_nofield = 0  # 급여 행 없음
    cnt_err     = 0  # 오류

    for idx, (db_id, post_id, url) in enumerate(posts, 1):
        try:
            raw = extract_salary_text(driver, url)
            cnt_total += 1

            if raw is None:
                # 급여 행 없음
                mark_fetched(conn, db_id)
                cnt_nofield += 1
            else:
                parsed = parse_salary(raw)
                save_salary(conn, db_id, raw, parsed)

                if parsed['salary_net_min'] is not None:
                    cnt_salary += 1
                elif parsed['salary_type'] is None:
                    cnt_nego += 1
                else:
                    # type/unit 있으나 숫자 파싱 실패
                    cnt_nofield += 1

        except Exception as e:
            log(f"  [오류] id={db_id} url={url}: {e}")
            mark_fetched(conn, db_id)
            cnt_err += 1
            cnt_total += 1

        # 딜레이
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        # 진행 출력
        if idx % PROGRESS_N == 0 or idx == total:
            elapsed = max(1, (datetime.now() - start).seconds)
            speed   = idx / elapsed * 60
            remain  = (total - idx) / speed if speed > 0 else 0
            log(
                f"  [{idx:>5}/{total}] "
                f"급여수집 {cnt_salary}건 | 협의 {cnt_nego}건 | "
                f"없음 {cnt_nofield}건 | 오류 {cnt_err}건 "
                f"| {speed:.0f}건/분 | 잔여 약 {remain:.0f}분"
            )

    # ── 최종 결과 ────────────────────────────────────────────
    elapsed_total = max(1, (datetime.now() - start).seconds)
    log("\n" + "=" * 62)
    log("  Backfill 완료!")
    log(f"  총 방문     : {cnt_total:,}건")
    log(f"  급여 수집   : {cnt_salary:,}건  (Net 환산 완료)")
    log(f"  협의/미정   : {cnt_nego:,}건  (salary_net = NULL)")
    log(f"  급여행 없음 : {cnt_nofield:,}건  (salary_net = NULL)")
    log(f"  오류        : {cnt_err:,}건")
    log(f"  소요 시간   : {elapsed_total // 60}분 {elapsed_total % 60}초")
    log("=" * 62)

    driver.quit()
    conn.close()
    _LOG.close()


if __name__ == '__main__':
    main()

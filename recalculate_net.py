#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recalculate_net.py — salary_net_min / salary_net_max 재계산
─────────────────────────────────────────────────────────────
변경 정책:
  · Net  공고 : 공고 기재 Net 그대로 저장 (퇴직금 미합산)
  · Gross 공고 : 세후 실수령 + Gross ÷ 12  (기존과 동일)

재크롤링 없이 DB 에 저장된 salary_min / salary_max / salary_type /
salary_unit 값만으로 salary_net_min · salary_net_max 를 업데이트합니다.

실행:
    python recalculate_net.py
"""

import sys
import psycopg2
from salary_calculator import calc_net_with_retirement

DB_CONFIG = {
    'host': 'localhost', 'port': 5432,
    'dbname': 'medigate', 'user': 'postgres', 'password': 'postgres',
}


def main():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print(f"DB 연결 실패: {e}")
        sys.exit(1)

    cur = conn.cursor()

    # 급여 파싱 완료 + 숫자가 있는 공고만 대상
    cur.execute("""
        SELECT id, salary_type, salary_unit, salary_min, salary_max
        FROM   recruit_posts
        WHERE  salary_type IS NOT NULL
          AND  salary_min  IS NOT NULL
        ORDER  BY id
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"재계산 대상: {total:,}건\n")

    updated = skipped = errors = 0

    for db_id, s_type, s_unit, s_min, s_max in rows:
        s_max = s_max if s_max is not None else s_min

        # 연봉 → 월급 환산 (만원 단위 유지)
        if s_unit == 'annual':
            m_min = s_min / 12.0
            m_max = s_max / 12.0
        else:
            m_min = float(s_min)
            m_max = float(s_max)

        try:
            if s_type == 'net':
                # 공고 기재 Net 그대로 (만원)
                net_min = round(m_min)
                net_max = round(m_max)

            elif s_type == 'gross':
                # 세후 실수령 + Gross/12 (원 → 만원 변환)
                net_min = round(
                    calc_net_with_retirement('gross', int(m_min * 10_000)) / 10_000
                )
                net_max = round(
                    calc_net_with_retirement('gross', int(m_max * 10_000)) / 10_000
                )

            else:
                skipped += 1
                continue

        except Exception as e:
            print(f"  [오류] id={db_id}: {e}")
            errors += 1
            continue

        cur.execute(
            "UPDATE recruit_posts SET salary_net_min = %s, salary_net_max = %s WHERE id = %s",
            (net_min, net_max, db_id),
        )
        updated += 1

    conn.commit()
    cur.close()
    conn.close()

    print("=" * 50)
    print(f"  업데이트 완료 : {updated:,}건")
    print(f"  건너뜀        : {skipped}건  (salary_type 불명확)")
    print(f"  오류          : {errors}건")
    print("=" * 50)


if __name__ == '__main__':
    main()

"""
app.py  –  개원비밀공간 구인 트렌드 Streamlit 대시보드

실행
----
    streamlit run app.py

기능
----
- 사이드바: 지역 / 진료과 필터 (드롭다운)
- 막대그래프: 월별 구인건수 (Plotly)
- 막대 클릭 → 팝업 다이얼로그: 해당 월 병원 목록 표시
- 급여 현황: 지역별 / 진료과별 평균 Net 월급 수평 막대 그래프
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine, text

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 페이지 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.set_page_config(
    page_title="개원비밀공간 구인 트렌드",
    page_icon="🏥",
    layout="wide",
)

DB_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/medigate"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DB 엔진 (앱 생명주기 동안 1회만 생성)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@st.cache_resource
def get_engine():
    return create_engine(DB_URL)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 마취통증의학과 전용 — 엑셀 + DB 병원 단위 통합 (1분 캐싱)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@st.cache_data(ttl=60)
def load_machwi_combined(region: str = "전체") -> pd.DataFrame:
    """엑셀 + DB 마취통증의학과 월별 데이터 통합 (지역 필터 지원).

    겹치는 월 (Excel·DB 모두 있는 경우):
      - hospital_name 기준으로 중복 제거
      - 동일 병원은 Excel 급여 우선 사용
      - DB에만 있는 병원은 DB 급여 추가
      - 출처 = '엑셀(과거)' (파랑)
    Excel만 있는 월: '엑셀(과거)' (파랑)
    DB만 있는 월:   'DB(크롤링)' (주황)
    """
    # ── 지역 필터 조건 생성 ────────────────────────────────────────────────────
    xl_params: dict = {"source": "excel_import"}
    db_params: dict = {}
    xl_region_cond = ""
    db_region_cond = ""

    if region != "전체":
        if len(region) > 2:          # 시도+시군 (예: 경기수원, 경북포항)
            sido = region[:2]
            city = region[2:]
            db_region_cond = "AND rp.region_sido = :sido AND rp.region LIKE :region_like"
            db_params["sido"]        = sido
            db_params["region_like"] = f"{sido} {city}%"
            # Excel region 형식 불일치 가능성 → 시도 단위로 필터
            xl_region_cond  = "AND meh.region LIKE :xl_sido || '%'"
            xl_params["xl_sido"] = sido
        else:                         # 시도 단위 (예: 서울, 경기)
            db_region_cond  = "AND rp.region_sido = :sido"
            db_params["sido"] = region
            xl_region_cond  = "AND meh.region LIKE :xl_sido || '%'"
            xl_params["xl_sido"] = region

    try:
        with get_engine().connect() as conn:
            # 엑셀 raw: 병원 단위
            df_xls = pd.read_sql(text(f"""
                SELECT meh.reg_month, meh.hospital_name, meh.net_pay
                FROM   machwi_excel_history meh
                WHERE  meh.source = :source
                {xl_region_cond}
            """), conn, params=xl_params)
            # DB raw: 병원 단위 (DISTINCT로 중복 진료과 제거)
            df_db = pd.read_sql(text(f"""
                SELECT DISTINCT
                    LEFT(rp.register_date, 7) AS reg_month,
                    rp.hospital_name,
                    CASE WHEN rp.salary_type = 'net'
                              AND rp.salary_unit = 'monthly'
                              AND rp.salary_net_min > 650
                              AND rp.salary_net_max > 650
                         THEN (rp.salary_net_min + rp.salary_net_max) / 2.0
                         ELSE NULL END AS net_pay
                FROM  recruit_posts rp
                JOIN  recruit_post_specialties rps ON rps.post_id = rp.id
                WHERE rps.specialty LIKE '%마취%'
                  AND rp.register_date IS NOT NULL
                  AND rp.register_date <> ''
                  {db_region_cond}
            """), conn, params=db_params)
    except Exception as e:
        st.error(f"마취통증 통합 데이터 조회 오류: {e}")
        return pd.DataFrame()

    xls_months = set(df_xls["reg_month"].unique())
    db_months  = set(df_db["reg_month"].unique())
    overlap    = xls_months & db_months
    xls_only   = xls_months - db_months
    db_only    = db_months  - xls_months

    records = []

    # ── 엑셀 전용 월 ──────────────────────────────────────────────────────────
    for month in xls_only:
        rows = df_xls[df_xls["reg_month"] == month]
        pays = rows["net_pay"].dropna()
        records.append({
            "등록월": month, "공고수": len(rows),
            "평균Net월급": round(float(pays.mean())) if len(pays) else None,
            "출처": "엑셀(과거)",
        })

    # ── DB 전용 월 ─────────────────────────────────────────────────────────────
    for month in db_only:
        rows = df_db[df_db["reg_month"] == month]
        pays = rows["net_pay"].dropna()
        records.append({
            "등록월": month, "공고수": len(rows),
            "평균Net월급": round(float(pays.mean())) if len(pays) else None,
            "출처": "DB(크롤링)",
        })

    # ── 겹치는 월: hospital_name 기준 병합, Excel 급여 우선 ────────────────────
    for month in overlap:
        xls_m = df_xls[df_xls["reg_month"] == month].copy()
        db_m  = df_db[df_db["reg_month"]  == month].copy()

        xls_m["h_key"] = xls_m["hospital_name"].str.strip()
        db_m["h_key"]  = db_m["hospital_name"].str.strip()

        xls_keys = set(xls_m["h_key"].dropna())

        # Excel 병원 전체 급여 + DB에만 있는 병원 급여
        db_extra = db_m[~db_m["h_key"].isin(xls_keys)]
        all_pays = (xls_m["net_pay"].dropna().tolist()
                    + db_extra["net_pay"].dropna().tolist())
        total_cnt = len(xls_m) + len(db_extra)

        records.append({
            "등록월": month, "공고수": total_cnt,
            "평균Net월급": round(sum(all_pays) / len(all_pays)) if all_pays else None,
            "출처": "엑셀(과거)",   # 엑셀 포함이므로 파랑
        })

    df = (pd.DataFrame(records)
          .sort_values("등록월")
          .reset_index(drop=True))
    return df


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 집계 데이터 로드 (60초 캐싱)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@st.cache_data(ttl=60)
def load_salary_monthly(region: str, specialty: str) -> pd.DataFrame:
    """월별 평균 Net 월급 집계 (메인 차트용, 봉직의 한정)."""
    conditions = [
        "rp.salary_net_min IS NOT NULL",
        "rp.salary_net_max IS NOT NULL",
        "rp.register_date IS NOT NULL",
        "rp.register_date <> ''",
        "rp.employment_type = '봉직의'",
        "(rp.salary_net_min + rp.salary_net_max) / 2.0 > 1300",
    ]
    params: dict = {}
    need_join = specialty != "전체"

    if region != "전체":
        if len(region) > 2:  # 시도+시군 조합 (예: 경기수원, 경북포항)
            sido = region[:2]
            city = region[2:]
            conditions.append("rp.region_sido = :region_sido")
            conditions.append("rp.region LIKE :region_like")
            params["region_sido"] = sido
            params["region_like"] = f"{sido} {city}%"
        else:
            conditions.append("rp.region_sido = :region")
            params["region"] = region
    if specialty != "전체":
        conditions.append("rps.specialty = :specialty")
        params["specialty"] = specialty

    where = " AND ".join(conditions)
    join  = "JOIN recruit_post_specialties rps ON rps.post_id = rp.id" if need_join else ""

    sql = text(f"""
        WITH base AS (
            SELECT
                LEFT(rp.register_date, 7)                      AS reg_month,
                (rp.salary_net_min + rp.salary_net_max) / 2.0 AS salary_mid
            FROM recruit_posts rp
            {join}
            WHERE {where}
        ),
        stats AS (
            SELECT
                reg_month,
                COUNT(*)                                                  AS cnt,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY salary_mid) AS q1,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY salary_mid) AS q3,
                PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY salary_mid) AS median_val
            FROM base
            GROUP BY reg_month
        ),
        filtered AS (
            SELECT b.reg_month, b.salary_mid, s.cnt, s.median_val
            FROM base b
            JOIN stats s ON s.reg_month = b.reg_month
            WHERE s.cnt < 15
               OR b.salary_mid BETWEEN s.q1 - 1.5 * (s.q3 - s.q1)
                                   AND s.q3 + 1.5 * (s.q3 - s.q1)
        )
        SELECT
            reg_month,
            ROUND(CASE WHEN MAX(cnt) >= 15 THEN AVG(salary_mid)
                       ELSE MAX(median_val) END) AS avg_net,
            MAX(cnt)                             AS cnt
        FROM filtered
        GROUP BY reg_month
        ORDER BY reg_month
    """)
    try:
        with get_engine().connect() as conn:
            df = pd.read_sql(sql, conn, params=params)
        return df.rename(columns={"reg_month": "등록월", "avg_net": "평균Net월급", "cnt": "공고수"})
    except Exception as e:
        st.error(f"급여 월별 조회 오류: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_salary_ranking(region: str, specialty: str) -> tuple:
    """지역별 / 진료과별 전체 평균 순위 (보조 테이블용, 봉직의 한정)."""
    params: dict = {}
    need_join = specialty != "전체"
    conditions_base = [
        "rp.salary_net_min IS NOT NULL",
        "rp.salary_net_max IS NOT NULL",
        "rp.employment_type = '봉직의'",
        "(rp.salary_net_min + rp.salary_net_max) / 2.0 > 1300",
    ]
    if region != "전체":
        if len(region) > 2:  # 시도+시군 조합 (예: 경기수원, 경북포항)
            sido = region[:2]
            city = region[2:]
            conditions_base.append("rp.region_sido = :region_sido")
            conditions_base.append("rp.region LIKE :region_like")
            params["region_sido"] = sido
            params["region_like"] = f"{sido} {city}%"
        else:
            conditions_base.append("rp.region_sido = :region")
            params["region"] = region
    if specialty != "전체":
        conditions_base.append("rps.specialty = :specialty")
        params["specialty"] = specialty

    join  = "JOIN recruit_post_specialties rps ON rps.post_id = rp.id" if need_join else ""
    where = " AND ".join(conditions_base)

    # 지역별 순위 (시도 단위)
    sql_r = text(f"""
        WITH base AS (
            SELECT
                rp.region_sido                                 AS region,
                (rp.salary_net_min + rp.salary_net_max) / 2.0 AS salary_mid
            FROM recruit_posts rp {join}
            WHERE {where}
              AND rp.region_sido IS NOT NULL AND rp.region_sido <> ''
        ),
        stats AS (
            SELECT
                region,
                COUNT(*)                                                  AS cnt,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY salary_mid) AS q1,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY salary_mid) AS q3,
                PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY salary_mid) AS median_val
            FROM base
            GROUP BY region
        ),
        filtered AS (
            SELECT b.region, b.salary_mid, s.cnt, s.median_val
            FROM base b
            JOIN stats s ON s.region = b.region
            WHERE s.cnt < 15
               OR b.salary_mid BETWEEN s.q1 - 1.5 * (s.q3 - s.q1)
                                   AND s.q3 + 1.5 * (s.q3 - s.q1)
        )
        SELECT
            region,
            ROUND(CASE WHEN MAX(cnt) >= 15 THEN AVG(salary_mid)
                       ELSE MAX(median_val) END) AS avg_net,
            MAX(cnt)                             AS cnt
        FROM filtered
        GROUP BY region
        ORDER BY avg_net DESC
    """)
    # 진료과별 순위
    join_s  = "JOIN recruit_post_specialties rps ON rps.post_id = rp.id"
    cond_s  = [c for c in conditions_base if "rps.specialty" not in c]
    where_s = " AND ".join(cond_s)
    sql_s = text(f"""
        WITH base AS (
            SELECT
                rps.specialty                                  AS specialty,
                (rp.salary_net_min + rp.salary_net_max) / 2.0 AS salary_mid
            FROM recruit_posts rp {join_s}
            WHERE {where_s}
        ),
        stats AS (
            SELECT
                specialty,
                COUNT(*)                                                  AS cnt,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY salary_mid) AS q1,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY salary_mid) AS q3,
                PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY salary_mid) AS median_val
            FROM base
            GROUP BY specialty
        ),
        filtered AS (
            SELECT b.specialty, b.salary_mid, s.cnt, s.median_val
            FROM base b
            JOIN stats s ON s.specialty = b.specialty
            WHERE s.cnt < 15
               OR b.salary_mid BETWEEN s.q1 - 1.5 * (s.q3 - s.q1)
                                   AND s.q3 + 1.5 * (s.q3 - s.q1)
        )
        SELECT
            specialty,
            ROUND(CASE WHEN MAX(cnt) >= 15 THEN AVG(salary_mid)
                       ELSE MAX(median_val) END) AS avg_net,
            MAX(cnt)                             AS cnt
        FROM filtered
        GROUP BY specialty
        HAVING MAX(cnt) >= 5
        ORDER BY avg_net DESC
    """)
    try:
        with get_engine().connect() as conn:
            df_r = pd.read_sql(sql_r, conn, params=params).rename(
                columns={"region": "지역", "avg_net": "평균Net월급", "cnt": "공고수"})
            df_s = pd.read_sql(sql_s, conn, params={k: v for k, v in params.items()
                                                    if k != "specialty"}).rename(
                columns={"specialty": "진료과", "avg_net": "평균Net월급", "cnt": "공고수"})
        return df_r, df_s
    except Exception as e:
        st.error(f"순위 조회 오류: {e}")
        return pd.DataFrame(), pd.DataFrame()


@st.cache_data(ttl=60)
def load_aggregated() -> pd.DataFrame:
    """(region, specialty, employment_type, reg_month, post_count) 집계 테이블 반환."""
    try:
        with get_engine().connect() as conn:
            return pd.read_sql(text("""
                SELECT
                    rp.region_sido            AS region,
                    rps.specialty             AS specialty,
                    rp.employment_type        AS employment_type,
                    LEFT(rp.register_date, 7) AS reg_month,
                    COUNT(DISTINCT rp.id)     AS post_count
                FROM  recruit_posts             rp
                JOIN  recruit_post_specialties  rps ON rps.post_id = rp.id
                WHERE rp.register_date IS NOT NULL
                  AND rp.register_date <> ''
                  AND rp.region_sido   IS NOT NULL
                  AND rp.region_sido   <> ''
                GROUP BY rp.region_sido, rps.specialty, rp.employment_type,
                         LEFT(rp.register_date, 7)
                UNION ALL
                SELECT
                    (rp.region_sido || REGEXP_REPLACE(
                        SPLIT_PART(rp.region, ' ', 2), '(시|군)$', ''
                    ))                        AS region,
                    rps.specialty             AS specialty,
                    rp.employment_type        AS employment_type,
                    LEFT(rp.register_date, 7) AS reg_month,
                    COUNT(DISTINCT rp.id)     AS post_count
                FROM  recruit_posts             rp
                JOIN  recruit_post_specialties  rps ON rps.post_id = rp.id
                WHERE rp.register_date IS NOT NULL
                  AND rp.register_date <> ''
                  AND rp.region        IS NOT NULL
                  AND rp.region        <> ''
                  AND SPLIT_PART(rp.region, ' ', 2) ~ '(시|군)$'
                GROUP BY (rp.region_sido || REGEXP_REPLACE(
                              SPLIT_PART(rp.region, ' ', 2), '(시|군)$', ''
                          )),
                         rps.specialty, rp.employment_type,
                         LEFT(rp.register_date, 7)
                ORDER BY reg_month
            """), conn)
    except Exception as e:
        st.error(f"DB 연결 오류: {e}")
        return pd.DataFrame(columns=["region", "specialty", "employment_type",
                                     "reg_month", "post_count"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 병원 목록 조회 (클릭 시 호출 — 캐싱 없음, 매번 최신 조회)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def load_hospitals(month: str, region: str, specialty: str,
                   employment_type: str) -> pd.DataFrame:
    """
    선택된 월·지역·진료과·고용형태 조건에 해당하는 병원 목록을 반환.
    각 병원의 진료과가 여러 개인 경우 콤마로 합쳐서 1행으로 표시.
    """
    conditions = [
        "LEFT(rp.register_date, 7) = :month",
        "rp.register_date IS NOT NULL",
        "rp.register_date <> ''",
    ]
    params: dict = {"month": month}

    if region != "전체":
        if len(region) > 2:  # 시도+시군 조합 (예: 경기수원, 경북포항)
            sido = region[:2]
            city = region[2:]
            conditions.append("rp.region_sido = :region_sido")
            conditions.append("rp.region LIKE :region_like")
            params["region_sido"] = sido
            params["region_like"] = f"{sido} {city}%"
        else:
            conditions.append("rp.region_sido = :region")
            params["region"] = region
    if specialty != "전체":
        conditions.append("rps.specialty = :specialty")
        params["specialty"] = specialty
    if employment_type != "전체":
        conditions.append("rp.employment_type = :employment_type")
        params["employment_type"] = employment_type

    where = " AND ".join(conditions)

    # 중복횟수: 동일 진료과 기준으로 카운트
    # · specialty 필터가 있으면 해당 과 포함 공고만 카운트
    # · 전체면 현재 공고와 진료과가 하나라도 겹치는 공고만 카운트
    if specialty != "전체":
        count_subq = """(
            SELECT COUNT(DISTINCT rp2.id)
            FROM  recruit_posts rp2
            JOIN  recruit_post_specialties rps2 ON rps2.post_id = rp2.id
            WHERE rp2.hospital_name   = rp.hospital_name
              AND rp2.region_sido     = rp.region_sido
              AND rp2.employment_type = rp.employment_type
              AND rps2.specialty      = :specialty
        )"""
    else:
        count_subq = """(
            SELECT COUNT(DISTINCT rp2.id)
            FROM  recruit_posts rp2
            JOIN  recruit_post_specialties rps2 ON rps2.post_id = rp2.id
            WHERE rp2.hospital_name   = rp.hospital_name
              AND rp2.region_sido     = rp.region_sido
              AND rp2.employment_type = rp.employment_type
              AND rps2.specialty IN (
                  SELECT specialty FROM recruit_post_specialties
                  WHERE post_id = rp.id
              )
        )"""

    sql = text(f"""
        SELECT
            rp.hospital_name                        AS 병원명,
            CASE
                WHEN rp.region IS NOT NULL AND rp.region <> ''
                     AND SPLIT_PART(rp.region, ' ', 2) ~ '(시|군)$'
                THEN rp.region_sido || REGEXP_REPLACE(
                         SPLIT_PART(rp.region, ' ', 2), '(시|군)$', ''
                     )
                ELSE rp.region_sido
            END                                     AS 지역,
            rp.employment_type                      AS 고용형태,
            STRING_AGG(DISTINCT rps.specialty, ', '
                       ORDER BY rps.specialty)      AS 진료과,
            rp.salary_raw                           AS salary_raw,
            rp.salary_net_min                       AS salary_net_min,
            rp.salary_net_max                       AS salary_net_max,
            rp.register_date                        AS 등록일,
            rp.url                                  AS 공고링크,
            {count_subq}                            AS recruit_count
        FROM  recruit_posts             rp
        JOIN  recruit_post_specialties  rps ON rps.post_id = rp.id
        WHERE {where}
        GROUP BY rp.id, rp.hospital_name, rp.region_sido, rp.region,
                 rp.employment_type,
                 rp.salary_raw, rp.salary_net_min, rp.salary_net_max,
                 rp.register_date, rp.url
        ORDER BY rp.hospital_name
    """)

    try:
        with get_engine().connect() as conn:
            df_db = pd.read_sql(sql, conn, params=params)
    except Exception as e:
        st.error(f"병원 목록 조회 오류: {e}")
        return pd.DataFrame()

    # ── 엑셀(machwi_excel_history) 데이터 병합 — 마취통증의학과 한정 ──────
    if specialty in ("전체", "마취통증의학과"):
        xl_region_params: dict = {}
        xl_region_cond = ""
        if region != "전체":
            sido = region[:2]
            xl_region_cond = "AND meh.region LIKE :xl_sido || '%'"
            xl_region_params["xl_sido"] = sido

        # Query 1: 전체 기간 엑셀 집계 (월 필터 없음) → DB 병원의 recruit_count 가산용
        xl_hist_sql = text(f"""
            SELECT hospital_name, COUNT(*) AS excel_count
            FROM machwi_excel_history meh
            WHERE source = 'excel_import'
              {xl_region_cond}
            GROUP BY hospital_name
        """)
        # Query 2: 클릭된 월의 엑셀 데이터 → 엑셀 전용 신규 행 추가용
        xl_month_sql = text(f"""
            SELECT meh.hospital_name, meh.region AS region, meh.net_pay
            FROM machwi_excel_history meh
            WHERE meh.reg_month = :xl_month
              AND meh.source    = 'excel_import'
              {xl_region_cond}
        """)
        try:
            with get_engine().connect() as conn:
                df_xl_hist  = pd.read_sql(xl_hist_sql, conn, params=xl_region_params)
                df_xl_month = pd.read_sql(xl_month_sql, conn,
                                          params={"xl_month": month, **xl_region_params})
        except Exception:
            df_xl_hist  = pd.DataFrame()
            df_xl_month = pd.DataFrame()

        # 전체 기간 카운트 맵: hospital_name → 누적 엑셀 등장 횟수
        xl_count_map: dict = {}
        if not df_xl_hist.empty:
            for _, row in df_xl_hist.iterrows():
                h = str(row["hospital_name"]).strip() if row["hospital_name"] else ""
                if h:
                    xl_count_map[h] = int(row["excel_count"])

        db_names = set(df_db["병원명"].str.strip()) if not df_db.empty else set()

        # Step 1: DB에 있는 병원에 전체 기간 엑셀 횟수 가산
        for h, ecnt in xl_count_map.items():
            if h in db_names:
                df_db.loc[df_db["병원명"].str.strip() == h, "recruit_count"] += ecnt

        # Step 2: 클릭된 월에 엑셀에만 있는 병원을 신규 행으로 추가
        new_rows = []
        if not df_xl_month.empty:
            for _, xl in df_xl_month.iterrows():
                h = str(xl["hospital_name"]).strip() if xl["hospital_name"] else ""
                if not h or h in db_names:
                    continue
                npay = float(xl["net_pay"]) if xl["net_pay"] is not None else None
                new_rows.append({
                    "병원명":         h,
                    "지역":           str(xl["region"]).strip() if xl["region"] else "-",
                    "고용형태":       "봉직의",
                    "진료과":         "마취통증의학과",
                    "salary_raw":     None,
                    "salary_net_min": npay,
                    "salary_net_max": npay,
                    "등록일":         month,
                    "공고링크":       None,
                    "recruit_count":  xl_count_map.get(h, 1),
                })
        if new_rows:
            df_db = pd.concat(
                [df_db, pd.DataFrame(new_rows)], ignore_index=True
            ).sort_values("병원명").reset_index(drop=True)

    return df_db


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 병원 구인 이력 조회
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def load_hospital_history(hospital_name: str, region_sido: str,
                          employment_type: str,
                          specialty: str = "전체") -> pd.DataFrame:
    """특정 병원의 구인 이력 (등록월·진료과·급여). specialty 필터 반영."""
    params = {
        "hospital_name":   hospital_name,
        "region_sido":     region_sido,
        "employment_type": employment_type,
    }
    # specialty 필터: 해당 과가 포함된 공고만 (전체면 전부 포함)
    if specialty != "전체":
        specialty_cond = """AND EXISTS (
            SELECT 1 FROM recruit_post_specialties s2
            WHERE s2.post_id = rp.id AND s2.specialty = :specialty
        )"""
        params["specialty"] = specialty
    else:
        specialty_cond = ""

    sql = text(f"""
        SELECT
            LEFT(rp.register_date, 7)               AS 등록월,
            (SELECT STRING_AGG(s.specialty, ', ' ORDER BY s.specialty)
             FROM   recruit_post_specialties s
             WHERE  s.post_id = rp.id)              AS 진료과,
            rp.salary_raw                           AS salary_raw,
            rp.salary_net_min                       AS salary_net_min,
            rp.salary_net_max                       AS salary_net_max,
            rp.url                                  AS 공고링크
        FROM  recruit_posts rp
        WHERE rp.hospital_name   = :hospital_name
          AND rp.region_sido     = :region_sido
          AND rp.employment_type = :employment_type
          {specialty_cond}
        ORDER BY rp.register_date
    """)
    try:
        with get_engine().connect() as conn:
            df = pd.read_sql(sql, conn, params=params)
    except Exception as e:
        st.error(f"구인 이력 조회 오류: {e}")
        return pd.DataFrame()

    # ── 엑셀 이력 추가 (machwi_excel_history) ──────────────────────────────
    xl_sql = text("""
        SELECT
            reg_month               AS 등록월,
            '마취통증의학과'         AS 진료과,
            NULL                    AS salary_raw,
            net_pay                 AS salary_net_min,
            net_pay                 AS salary_net_max,
            '[엑셀]'                AS 공고링크
        FROM machwi_excel_history
        WHERE hospital_name = :hospital_name
          AND source        = 'excel_import'
        ORDER BY reg_month
    """)
    try:
        with get_engine().connect() as conn:
            df_xl = pd.read_sql(xl_sql, conn, params={"hospital_name": hospital_name})
    except Exception:
        df_xl = pd.DataFrame()

    if not df_xl.empty:
        df = pd.concat([df, df_xl], ignore_index=True).sort_values("등록월").reset_index(drop=True)

    return df


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 팝업 다이얼로그 — 병원 목록
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@st.dialog("🏥 병원 목록", width="large")
def show_hospital_dialog(month: str, region: str, specialty: str,
                         employment_type: str):
    """막대 클릭 시 열리는 모달: 해당 월·조건의 병원 리스트."""

    # 헤더 정보
    region_label    = region          if region          != "전체" else "전체 지역"
    specialty_label = specialty       if specialty       != "전체" else "전체 진료과"
    emp_label       = employment_type if employment_type != "전체" else "전체 고용형태"
    st.markdown(
        f"**{month}** · {region_label} · {specialty_label} · {emp_label}",
        help="현재 적용된 필터 조건이 그대로 반영됩니다.",
    )
    st.divider()

    df_h = load_hospitals(month, region, specialty, employment_type)

    if df_h.empty:
        st.info("해당 조건의 병원 데이터가 없습니다.")
        return

    # ── 포맷 헬퍼 ──────────────────────────────────────────────────────────
    def format_salary(row):
        mn = row.get("salary_net_min")
        mx = row.get("salary_net_max")
        raw = row.get("salary_raw") or ""
        if mn is None or (isinstance(mn, float) and pd.isna(mn)):
            return raw[:20] + "…" if len(raw) > 20 else (raw or "-")
        mn, mx = int(mn), int(mx)
        if mn == mx:
            return f"{mn:,}만원"
        return f"{mn:,}~{mx:,}만원"

    def format_count(n):
        n = int(n)
        if n > 1:
            return f'<b style="color:#d32f2f">{n}회</b>'
        return f"{n}회"

    def make_link(url):
        if url and str(url).startswith("http"):
            return f'<a href="{url}" target="_blank">🔗 보기</a>'
        if url == "[엑셀]":
            return '<span style="color:#2196F3;font-size:11px">📊 엑셀</span>'
        return "-"

    # ── 구인 이력 조회 (상단) ──────────────────────────────────────────────
    repeat_df = (
        df_h[df_h["recruit_count"] > 1][["병원명", "지역", "고용형태"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    if not repeat_df.empty:
        st.markdown("#### 🔍 구인 이력 조회")
        st.caption(
            f"2회 이상 구인 공고를 올린 병원 **{len(repeat_df)}곳** — "
            "아래에서 병원을 선택하면 전체 이력을 확인할 수 있습니다."
        )
        options_map = {
            f"{r['병원명']}  ({r['지역']} / {r['고용형태']})": (
                r["병원명"], r["지역"], r["고용형태"]
            )
            for _, r in repeat_df.iterrows()
        }
        sel = st.selectbox(
            "병원 선택", ["─ 선택하세요 ─"] + list(options_map.keys()),
            key="hosp_hist_sel",
        )
        if sel != "─ 선택하세요 ─":
            h_name, h_region, h_emp = options_map[sel]
            df_hist = load_hospital_history(h_name, h_region, h_emp, specialty)
            if df_hist.empty:
                st.info("이력 데이터가 없습니다.")
            else:
                st.caption(
                    f"**{h_name}** ({h_region} / {h_emp})  —  총 {len(df_hist)}건"
                )

                # ── 차트 데이터 준비 (포맷 전 원본 사용) ───────────────────
                df_chart = df_hist.copy()
                df_chart["출처"] = df_chart["공고링크"].apply(
                    lambda u: "A (엑셀)" if u == "[엑셀]" else "B (DB)"
                )
                df_chart["net_pay"] = df_chart.apply(
                    lambda r: (
                        (float(r["salary_net_min"]) + float(r["salary_net_max"])) / 2
                        if pd.notna(r.get("salary_net_min")) and pd.notna(r.get("salary_net_max"))
                        else None
                    ), axis=1,
                )
                df_chart = df_chart[df_chart["net_pay"].notna()].sort_values("등록월")

                # ── 테이블 + 차트 나란히 ──────────────────────────────────
                col_tbl, col_chart = st.columns([1, 1])

                with col_tbl:
                    df_disp = df_hist.copy()
                    df_disp.insert(2, "Net월급(퇴직금포함)", df_disp.apply(format_salary, axis=1))
                    df_disp["공고링크"] = df_disp["공고링크"].apply(make_link)
                    df_disp = df_disp.drop(
                        columns=["salary_raw", "salary_net_min", "salary_net_max"]
                    )
                    st.markdown(
                        df_disp.to_html(escape=False, index=False),
                        unsafe_allow_html=True,
                    )

                with col_chart:
                    if not df_chart.empty:
                        fig_h = go.Figure()
                        color_map = {"A (엑셀)": "#1976D2", "B (DB)": "#F57C00"}
                        for src in ["A (엑셀)", "B (DB)"]:
                            d = df_chart[df_chart["출처"] == src]
                            if d.empty:
                                continue
                            fig_h.add_trace(go.Scatter(
                                x=d["등록월"],
                                y=d["net_pay"],
                                mode="lines+markers",
                                name=src,
                                line=dict(color=color_map[src], width=2),
                                marker=dict(size=8),
                                hovertemplate="%{x}<br><b>%{y:,.0f}만원</b><extra></extra>",
                            ))
                        # A-B 구간 연결선 (점선)
                        d_a = df_chart[df_chart["출처"] == "A (엑셀)"].sort_values("등록월")
                        d_b = df_chart[df_chart["출처"] == "B (DB)"].sort_values("등록월")
                        if not d_a.empty and not d_b.empty:
                            fig_h.add_trace(go.Scatter(
                                x=[d_a.iloc[-1]["등록월"], d_b.iloc[0]["등록월"]],
                                y=[d_a.iloc[-1]["net_pay"], d_b.iloc[0]["net_pay"]],
                                mode="lines",
                                line=dict(color="#aaa", width=1.5, dash="dot"),
                                showlegend=False,
                                hoverinfo="skip",
                            ))
                        fig_h.update_layout(
                            title=dict(text="📈 Net월급 시계열 추이", font=dict(size=13)),
                            xaxis=dict(title=None, tickangle=-45, tickfont=dict(size=10)),
                            yaxis=dict(title="만원", tickformat=","),
                            legend=dict(orientation="h", y=1.12, x=0),
                            margin=dict(l=40, r=10, t=55, b=60),
                            height=340,
                            plot_bgcolor="#fafafa",
                        )
                        st.plotly_chart(fig_h, use_container_width=True)
                    else:
                        st.info("급여 데이터가 없어 차트를 그릴 수 없습니다.")
        st.divider()

    # ── 병원 목록 표 ───────────────────────────────────────────────────────
    st.caption(f"총 **{len(df_h)}개** 병원")
    display = df_h.copy()
    display.insert(4, "Net월급(퇴직금포함)", display.apply(format_salary, axis=1))
    display.insert(6, "중복횟수", display["recruit_count"].apply(format_count))
    display["공고링크"] = display["공고링크"].apply(make_link)
    display = display.drop(
        columns=["salary_raw", "salary_net_min", "salary_net_max", "recruit_count"]
    )
    st.markdown(
        display.to_html(escape=False, index=False),
        unsafe_allow_html=True,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 사이드바 — 필터
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with st.sidebar:
    st.header("🔍 필터")

    df_all = load_aggregated()

    if df_all.empty:
        st.warning("데이터가 없거나 DB 연결에 실패했습니다.")
        st.stop()

    # 전체 목록 (지역·진료과 서로 독립 — 상호 종속 없음)
    _all_regions     = ["전체"] + sorted(df_all["region"].dropna().unique().tolist())
    _all_specialties = ["전체"] + sorted(df_all["specialty"].dropna().unique().tolist())

    # ── 지역 검색 + 드롭다운 ─────────────────────────────────────────────────
    st.markdown("**📍 지역**")
    _region_q = st.text_input(
        "지역 검색", key="region_q",
        placeholder="예: 서울, 경기수원, 부산…",
        label_visibility="collapsed",
    )
    _region_q_strip = _region_q.strip()
    _region_opts = (
        [r for r in _all_regions if _region_q_strip in r]
        if _region_q_strip else _all_regions
    ) or ["전체"]

    selected_region = st.selectbox(
        "지역 선택", _region_opts,
        key="region_box", label_visibility="collapsed",
    )

    # ── 진료과 검색 + 드롭다운 ───────────────────────────────────────────────
    st.markdown("**🩺 진료과**")
    _spec_q = st.text_input(
        "진료과 검색", key="specialty_q",
        placeholder="예: 마취, 내과, 정형외과…",
        label_visibility="collapsed",
    )
    _spec_q_strip = _spec_q.strip()
    _spec_opts = (
        [s for s in _all_specialties if _spec_q_strip in s]
        if _spec_q_strip else _all_specialties
    ) or ["전체"]

    selected_specialty = st.selectbox(
        "진료과 선택", _spec_opts,
        key="specialty_box", label_visibility="collapsed",
    )

    st.divider()
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 필터링 & 월별 집계  (employment_type 필터는 차트 섹션에서 선택 후 적용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
df = df_all.copy()
if selected_region    != "전체":
    df = df[df["region"]    == selected_region]
if selected_specialty != "전체":
    df = df[df["specialty"] == selected_specialty]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 화면
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.title("🏥 구인 트렌드 대시보드")
st.caption(f"필터 적용 중 → 지역: **{selected_region}** · 진료과: **{selected_specialty}**")
st.divider()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 막대그래프 — 제목 + 고용형태 드롭다운 (인라인)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 고용형태 목록: DB 실제 값 기준 (건수 많은 순 고정 정렬)
EMPLOYMENT_TYPES = [
    "전체", "봉직의", "대진의", "당직의", "전임의", "전공의",
    "입원전담전문의", "출장검진", "임상(사내의사)", "임상외", "동업", "기타",
]

col_title, col_emp = st.columns([5, 2])
with col_title:
    st.subheader("📊 월별 구인건수")
    st.caption("💡 막대를 클릭하면 해당 월의 병원 목록을 확인할 수 있습니다.")
with col_emp:
    st.markdown("<br>", unsafe_allow_html=True)   # 제목과 높이 맞춤
    selected_employment = st.selectbox(
        "👔 고용형태",
        EMPLOYMENT_TYPES,
        index=0,                   # 기본값: 전체
        key="employment_filter",
    )

# 고용형태 필터 적용 후 월별 집계
df_emp = df.copy()
if selected_employment != "전체":
    df_emp = df_emp[df_emp["employment_type"] == selected_employment]

df_monthly = (
    df_emp.groupby("reg_month")["post_count"]
    .sum().reset_index().sort_values("reg_month")
)
df_monthly["reg_month"] = df_monthly["reg_month"].astype(str)

# ── KPI 카드 ───────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
total_posts  = int(df_monthly["post_count"].sum()) if not df_monthly.empty else 0
col1.metric("총 공고 수",  f"{total_posts:,}건")
col2.metric("집계 월 수",  f"{len(df_monthly)}개월")
if not df_monthly.empty:
    peak = df_monthly.loc[df_monthly["post_count"].idxmax()]
    col3.metric("최고 공고월", f"{peak['reg_month']} ({int(peak['post_count'])}건)")
else:
    col3.metric("최고 공고월", "-")

st.divider()

if df_monthly.empty:
    st.warning("선택한 조건에 해당하는 데이터가 없습니다.")
else:
    fig = px.bar(
        df_monthly,
        x="reg_month",
        y="post_count",
        text="post_count",
        labels={"reg_month": "등록 월", "post_count": "공고 수"},
        color_discrete_sequence=["#2196F3"],
        category_orders={"reg_month": sorted(df_monthly["reg_month"].tolist())},
    )
    fig.update_traces(
        textposition="outside",
        textfont_size=12,
        hovertemplate="<b>%{x}</b><br>공고 수: <b>%{y}건</b>  ← 클릭하세요<extra></extra>",
    )
    fig.update_layout(
        xaxis_title="등록 월",
        yaxis_title="공고 수",
        plot_bgcolor="white",
        xaxis=dict(tickangle=-30, type="category"),
        yaxis=dict(
            gridcolor="#eeeeee",
            zeroline=True,
            range=[0, df_monthly["post_count"].max() * 1.25],
        ),
        bargap=0.35,
        height=460,
        margin=dict(t=30, b=50, l=50, r=20),
        hoverlabel=dict(bgcolor="white", font_size=13),
        # 클릭 가능함을 커서로 암시
        clickmode="event",
    )

    # on_select="rerun": 클릭 시 앱 재실행 + 선택 정보 반환
    event = st.plotly_chart(
        fig,
        use_container_width=True,
        on_select="rerun",
        selection_mode="points",
        key="bar_chart",
    )

    # 클릭된 막대가 있으면 다이얼로그 열기
    points = event.selection.get("points", []) if event.selection else []
    if points:
        clicked_month = str(points[0].get("x", ""))
        if clicked_month:
            show_hospital_dialog(
                clicked_month, selected_region,
                selected_specialty, selected_employment,
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 상세 데이터 테이블
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with st.expander("📋 상세 데이터 테이블 보기"):
    if df_emp.empty:
        st.info("데이터가 없습니다.")
    else:
        st.dataframe(
            df_emp.sort_values(["reg_month", "region", "specialty"])
            .rename(columns={
                "region":          "지역",
                "specialty":       "진료과",
                "employment_type": "고용형태",
                "reg_month":       "등록 월",
                "post_count":      "공고 수",
            })
            .reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 급여 현황 — 월별 Net 월급 추이
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.divider()
st.subheader("💰 급여 현황 — 월별 평균 Net 월급 추이 (봉직의)")
st.caption(
    "봉직의 공고 한정 · Net 월급 기준 · 인센티브 비포함 · 협의/미기재 공고 제외 · "
    "15건 이상 그룹: IQR 이상치 제거 후 평균 · 15건 미만 그룹: 중앙값"
)

# ── 데이터 로드 (사이드바 필터 그대로 사용) ───────────────────────────────
df_sal = load_salary_monthly(selected_region, selected_specialty)

# ── KPI 카드 ───────────────────────────────────────────────────────────────
sk1, sk2, sk3 = st.columns(3)

if not df_sal.empty:
    total_cnt = int(df_sal["공고수"].sum())
    overall_avg = int(
        (df_sal["평균Net월급"] * df_sal["공고수"]).sum() / df_sal["공고수"].sum()
    )
    peak = df_sal.loc[df_sal["평균Net월급"].idxmax()]
    sk1.metric("집계 공고 수", f"{total_cnt:,}건")
    sk2.metric("전체 기간 평균", f"{overall_avg:,}만원")
    sk3.metric("최고 평균 월", f"{peak['등록월']} ({int(peak['평균Net월급']):,}만원)")
else:
    sk1.metric("집계 공고 수", "-")
    sk2.metric("전체 기간 평균", "-")
    sk3.metric("최고 평균 월", "-")

st.divider()

# ── 월별 막대 그래프 ────────────────────────────────────────────────────────
if df_sal.empty:
    st.info("선택한 조건에 해당하는 급여 데이터가 없습니다.")
else:
    region_label    = selected_region    if selected_region    != "전체" else "전국"
    specialty_label = selected_specialty if selected_specialty != "전체" else "전체 진료과"
    chart_title = f"{region_label} · {specialty_label} 월별 평균 Net 월급"

    fig_sal = px.bar(
        df_sal,
        x="등록월",
        y="평균Net월급",
        text=df_sal["평균Net월급"].apply(lambda v: f"{int(v):,}만원"),
        custom_data=["공고수"],
        color_discrete_sequence=["#43A047"],
        category_orders={"등록월": sorted(df_sal["등록월"].tolist())},
        title=chart_title,
    )
    fig_sal.update_traces(
        textposition="outside",
        textfont_size=12,
        hovertemplate=(
            "<b>%{x}</b><br>"
            "평균 Net 월급: <b>%{y:,}만원</b><br>"
            "집계 공고: %{customdata[0]}건<extra></extra>"
        ),
    )
    fig_sal.update_layout(
        xaxis_title="등록 월",
        yaxis_title="평균 Net 월급 (만원)",
        plot_bgcolor="white",
        xaxis=dict(tickangle=-30, type="category"),
        yaxis=dict(
            gridcolor="#eeeeee",
            zeroline=True,
            range=[
                max(0, df_sal["평균Net월급"].min() * 0.85),
                df_sal["평균Net월급"].max() * 1.15,
            ],
        ),
        bargap=0.35,
        height=460,
        margin=dict(t=50, b=50, l=60, r=20),
        hoverlabel=dict(bgcolor="white", font_size=13),
        title_font_size=15,
    )
    st.plotly_chart(fig_sal, use_container_width=True)

# ── 지역별 / 진료과별 전체 순위 (참고용) ──────────────────────────────────
_spec_label = selected_specialty if selected_specialty != "전체" else "전체 진료과"
_expander_title = (
    f"📊 지역별 · 진료과별 평균 순위 보기  |  진료과: {_spec_label}"
    if selected_specialty != "전체"
    else "📊 지역별 · 진료과별 평균 순위 보기"
)

with st.expander(_expander_title):
    df_rank_r, df_rank_s = load_salary_ranking(selected_region, selected_specialty)
    tab_r, tab_s = st.tabs(["📍 지역별", "🩺 진료과별"])

    with tab_r:
        if df_rank_r.empty:
            st.info("데이터가 없습니다.")
        else:
            st.caption(
                f"진료과 기준: **{_spec_label}** "
                f"{'· 해당 진료과 공고만 집계' if selected_specialty != '전체' else '· 전체 진료과 공고 집계'}"
            )
            df_plot_r = df_rank_r.head(17).sort_values("평균Net월급")
            fig_r = px.bar(
                df_plot_r,
                x="평균Net월급", y="지역", orientation="h",
                text=df_plot_r["평균Net월급"].apply(lambda v: f"{int(v):,}만원"),
                custom_data=["공고수"],
                color="평균Net월급", color_continuous_scale="Blues",
                title=f"지역별 평균 Net 월급 ({_spec_label})",
            )
            fig_r.update_traces(
                textposition="outside", textfont_size=11,
                hovertemplate=(
                    "<b>%{y}</b><br>평균 Net 월급: <b>%{x:,}만원</b><br>"
                    "집계 공고: %{customdata[0]}건<extra></extra>"
                ),
            )
            fig_r.update_layout(
                xaxis_title="평균 Net 월급 (만원)", yaxis_title="",
                plot_bgcolor="white", xaxis=dict(gridcolor="#eeeeee"),
                coloraxis_showscale=False,
                height=max(300, len(df_plot_r) * 36),
                margin=dict(t=40, b=40, l=10, r=80),
                title_font_size=14,
            )
            st.plotly_chart(fig_r, use_container_width=True)

    with tab_s:
        if df_rank_s.empty:
            st.info("데이터가 없습니다.")
        else:
            df_plot_s = df_rank_s.head(20).sort_values("평균Net월급")
            fig_s = px.bar(
                df_plot_s,
                x="평균Net월급", y="진료과", orientation="h",
                text=df_plot_s["평균Net월급"].apply(lambda v: f"{int(v):,}만원"),
                custom_data=["공고수"],
                color="평균Net월급", color_continuous_scale="Greens",
            )
            fig_s.update_traces(
                textposition="outside", textfont_size=11,
                hovertemplate=(
                    "<b>%{y}</b><br>평균 Net 월급: <b>%{x:,}만원</b><br>"
                    "집계 공고: %{customdata[0]}건<extra></extra>"
                ),
            )
            fig_s.update_layout(
                xaxis_title="평균 Net 월급 (만원)", yaxis_title="",
                plot_bgcolor="white", xaxis=dict(gridcolor="#eeeeee"),
                coloraxis_showscale=False,
                height=max(300, len(df_plot_s) * 36),
                margin=dict(t=10, b=40, l=10, r=80),
            )
            st.plotly_chart(fig_s, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 마취통증의학과 장기 트렌드 — 엑셀(과거) + DB(크롤링) 통합
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if selected_specialty == "마취통증의학과":
    st.divider()
    st.subheader("💉 마취통증의학과 장기 트렌드 (엑셀 과거자료 + DB 통합)")
    _region_label = selected_region if selected_region != "전체" else "전국"
    st.caption(
        f"엑셀: 2023-03 ~ 2026-01 (수동 수집 · Net 월급 기준) │ "
        f"DB: 크롤링 데이터 (net/monthly 공고만 급여 집계) │ "
        f"겹치는 월: 병원명 기준 중복 제거 후 단일 막대 (엑셀 급여 우선) │ "
        f"지역: **{_region_label}**"
    )

    df_combined = load_machwi_combined(selected_region)

    if df_combined.empty:
        st.warning("마취통증의학과 데이터를 불러올 수 없습니다.")
    else:
        # ── KPI 카드 ───────────────────────────────────────────────────────
        xls_rows = df_combined[df_combined["출처"] == "엑셀(과거)"]
        dbc_rows = df_combined[df_combined["출처"] == "DB(크롤링)"]
        kc1, kc2, kc3, kc4 = st.columns(4)
        kc1.metric("총 수집 개월수", f"{len(df_combined)}개월")
        kc2.metric("엑셀 / DB 개월수", f"{len(xls_rows)} / {len(dbc_rows)}")
        sal_rows = df_combined.dropna(subset=["평균Net월급"])
        if not sal_rows.empty:
            w_avg = int(
                (sal_rows["평균Net월급"] * sal_rows["공고수"]).sum()
                / sal_rows["공고수"].sum()
            )
            kc3.metric("전체 가중 평균 Net 월급", f"{w_avg:,}만원")
        else:
            kc3.metric("전체 가중 평균 Net 월급", "-")
        kc4.metric("총 공고수", f"{df_combined['공고수'].sum():,}건")

        st.divider()

        COLOR_XLS = "#2196F3"
        COLOR_DBC = "#FF9800"
        ANNOT_STYLE = dict(
            xref="paper", yref="paper",
            showarrow=False,
            font=dict(color="red", size=12, family="Arial"),
            align="left",
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="red",
            borderwidth=1,
            borderpad=5,
        )

        # 차트용 출처 표시: "엑셀(과거)" → "A", "DB(크롤링)" → "B"
        df_plot = df_combined.copy()
        df_plot["출처"] = df_plot["출처"].replace({"엑셀(과거)": "A", "DB(크롤링)": "B"})

        # ── 차트 1: 월별 구인 공고수 ──────────────────────────────────────
        st.markdown("#### 📊 월별 구인 공고수")
        fig_cnt = px.bar(
            df_plot,
            x="등록월", y="공고수",
            color="출처",
            color_discrete_map={"A": COLOR_XLS, "B": COLOR_DBC},
            text="공고수",
            barmode="group",
        )
        fig_cnt.update_traces(textposition="outside")

        # 공고수 12개월 이동평균 추세선
        show_ma_cnt = st.checkbox("추세선 표시 (12개월 이동평균)", value=True, key="ma_cnt")
        if show_ma_cnt:
            _cnt_ma = (
                df_plot.sort_values("등록월")[["등록월", "공고수"]]
                .assign(MA=lambda d: d["공고수"].rolling(12, min_periods=3).mean().round(1))
            )
            fig_cnt.add_trace(go.Scatter(
                x=_cnt_ma["등록월"],
                y=_cnt_ma["MA"],
                mode="lines",
                name="추세선 (12개월 MA)",
                line=dict(color="#000000", width=2.5),
                hovertemplate="<b>%{x}</b><br>이동평균: <b>%{y:.1f}건</b><extra></extra>",
            ))

        fig_cnt.update_layout(
            xaxis=dict(title="등록 월", tickangle=-30, type="category",
                       categoryorder="category ascending"),
            yaxis=dict(title="공고 수", gridcolor="#eeeeee", zeroline=True),
            plot_bgcolor="white",
            bargap=0.25, bargroupgap=0.1, height=450,
            margin=dict(t=20, b=60, l=50, r=20),
            legend=dict(title="", orientation="h", yanchor="bottom", y=1.02,
                        xanchor="right", x=1),
            hoverlabel=dict(bgcolor="white", font_size=13),
        )
        fig_cnt.add_annotation(
            x=0.01, y=0.97,
            text="A: 인센티브 포함(+200만원)　B: 인센티브 비포함",
            **ANNOT_STYLE,
        )
        st.plotly_chart(fig_cnt, use_container_width=True)

        # ── 차트 2: 월별 평균 Net 월급 ────────────────────────────────────
        st.markdown("#### 💰 월별 평균 Net 월급 추이")
        adjust_incentive = st.checkbox(
            "인센티브 보정 적용 — B에 +200만원 추가 (A와 비교 가능한 수준으로 보정)",
            value=True,
        )
        st.caption("A: 공고 기재 급여 평균 (인센티브 포함) │ B: net/monthly 공고만 집계 (인센티브 미포함)")

        df_sal = df_plot.dropna(subset=["평균Net월급"]).sort_values("등록월").copy()

        # 인센티브 보정: B 계열에 +200 적용
        if adjust_incentive:
            df_sal.loc[df_sal["출처"] == "B", "평균Net월급"] += 200

        d_a = df_sal[df_sal["출처"] == "A"]
        d_b = df_sal[df_sal["출처"] == "B"]
        b_label = "B (+200 보정)" if adjust_incentive else "B"

        fig_sal = go.Figure()
        for d, src, label, color, dash in [
            (d_a, "A", "A",      COLOR_XLS, "solid"),
            (d_b, "B", b_label,  COLOR_DBC, "dash"),
        ]:
            if d.empty:
                continue
            fig_sal.add_trace(go.Scatter(
                x=d["등록월"],
                y=d["평균Net월급"],
                mode="lines+markers+text",
                name=label,
                line=dict(color=color, width=2, dash=dash),
                marker=dict(size=7),
                text=d["평균Net월급"].apply(lambda v: f"{int(v):,}"),
                textposition="top center",
                textfont=dict(size=10, color=color),
                hovertemplate=(
                    f"<b>%{{x}}</b><br>평균 Net 월급: <b>%{{y:,}}만원</b> [{label}]<extra></extra>"
                ),
            ))

        # ── A-B 연결선 (마지막 A점 → 첫 번째 B점) ───────────────────────────
        if not d_a.empty and not d_b.empty:
            last_a  = d_a.iloc[-1]
            first_b = d_b.iloc[0]
            fig_sal.add_trace(go.Scatter(
                x=[last_a["등록월"], first_b["등록월"]],
                y=[last_a["평균Net월급"], first_b["평균Net월급"]],
                mode="lines",
                line=dict(color="gray", width=1.5, dash="dot"),
                showlegend=False,
                hoverinfo="skip",
            ))

        # ── 급여 12개월 이동평균 추세선 ────────────────────────────────────────
        show_ma_sal = st.checkbox("추세선 표시 (12개월 이동평균)", value=True, key="ma_sal")
        if show_ma_sal:
            _sal_ma = (
                df_sal.sort_values("등록월")[["등록월", "평균Net월급"]]
                .assign(MA=lambda d: d["평균Net월급"].rolling(12, min_periods=3).mean().round(0))
            )
            fig_sal.add_trace(go.Scatter(
                x=_sal_ma["등록월"],
                y=_sal_ma["MA"],
                mode="lines",
                name="추세선 (12개월 MA)",
                line=dict(color="#000000", width=2.5),
                hovertemplate="<b>%{x}</b><br>이동평균: <b>%{y:,.0f}만원</b><extra></extra>",
            ))

        all_vals = df_sal["평균Net월급"].tolist()
        y_min = max(0, min(all_vals) * 0.90) if all_vals else 0
        y_max = max(all_vals) * 1.12         if all_vals else 5000
        annot_sal = (
            "A: 인센티브 포함　　B: +200만원 보정 적용"
            if adjust_incentive else
            "A: 인센티브 포함(+200만원)　B: 인센티브 비포함"
        )
        fig_sal.update_layout(
            xaxis=dict(title="등록 월", tickangle=-30, type="category",
                       categoryorder="category ascending"),
            yaxis=dict(title="평균 Net 월급 (만원)", gridcolor="#eeeeee",
                       zeroline=False, range=[y_min, y_max]),
            plot_bgcolor="white", height=460,
            margin=dict(t=20, b=60, l=60, r=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hoverlabel=dict(bgcolor="white", font_size=13),
        )
        fig_sal.add_annotation(
            x=0.01, y=0.97,
            text=annot_sal,
            **ANNOT_STYLE,
        )
        st.plotly_chart(fig_sal, use_container_width=True)

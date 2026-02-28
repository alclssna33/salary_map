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

DB_URL = st.secrets["DB_URL"]


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
            # Excel region 형식: "경기화성", "경기수원" 등 시도+시군 형태로 저장
            xl_region_cond  = "AND meh.region LIKE :xl_region || '%'"
            xl_params["xl_region"] = region  # 예: "경기화성"
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
                  AND rp.employment_type = '봉직의'
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
                    rp.region_sido                  AS region,
                    rps.specialty                   AS specialty,
                    rp.employment_type              AS employment_type,
                    LEFT(rp.register_date, 7)       AS reg_month,
                    COUNT(DISTINCT rp.hospital_name) AS post_count
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
                    ))                               AS region,
                    rps.specialty                    AS specialty,
                    rp.employment_type               AS employment_type,
                    LEFT(rp.register_date, 7)        AS reg_month,
                    COUNT(DISTINCT rp.hospital_name) AS post_count
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
# 전국 지도 & 흐름 보기 — 시도별/시군구별 월별 집계 (Tab2 전용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@st.cache_data(ttl=60)
def load_national_trend(specialty: str, employment_type: str) -> pd.DataFrame:
    """시도별·월별 구인건수 + 평균 Net 페이 집계 (Tab2 스몰 멀티플즈·버블맵 공용).

    반환 컬럼: region_sido, reg_month, cnt, avg_pay
    - avg_pay: salary_net_min > 1300 조건, 없으면 None
    - 마취통증의학과 선택 시 machwi_excel_history 데이터도 합산
    """
    conditions = [
        "rp.register_date IS NOT NULL",
        "rp.register_date <> ''",
        "rp.region_sido   IS NOT NULL",
        "rp.region_sido   <> ''",
    ]
    params: dict = {}
    need_spec_join = specialty != "전체"

    if specialty != "전체":
        conditions.append("rps.specialty = :specialty")
        params["specialty"] = specialty
    if employment_type != "전체":
        conditions.append("rp.employment_type = :employment_type")
        params["employment_type"] = employment_type

    join = "JOIN recruit_post_specialties rps ON rps.post_id = rp.id" if need_spec_join else ""
    where = " AND ".join(conditions)

    sql = text(f"""
        SELECT
            rp.region_sido                          AS region_sido,
            LEFT(rp.register_date, 7)               AS reg_month,
            COUNT(DISTINCT rp.id)                   AS cnt,
            ROUND(AVG(CASE
                WHEN rp.salary_net_min > 1300 AND rp.salary_net_max > 1300
                THEN (rp.salary_net_min + rp.salary_net_max) / 2.0
                ELSE NULL END))                     AS avg_pay
        FROM recruit_posts rp
        {join}
        WHERE {where}
        GROUP BY rp.region_sido, LEFT(rp.register_date, 7)
        ORDER BY reg_month
    """)
    try:
        with get_engine().connect() as conn:
            df_db = pd.read_sql(sql, conn, params=params)
    except Exception as e:
        st.error(f"전국 트렌드 조회 오류: {e}")
        return pd.DataFrame()

    # ── 마취통증의학과: Excel 데이터 합산 ─────────────────────────────────────
    if specialty in ("전체", "마취통증의학과"):
        try:
            with get_engine().connect() as conn:
                df_xl = pd.read_sql(text("""
                    SELECT
                        LEFT(meh.region, 2)   AS region_sido,
                        meh.reg_month         AS reg_month,
                        COUNT(*)              AS cnt,
                        ROUND(AVG(meh.net_pay)) AS avg_pay
                    FROM machwi_excel_history meh
                    WHERE meh.source = 'excel_import'
                    GROUP BY LEFT(meh.region, 2), meh.reg_month
                """), conn)
        except Exception:
            df_xl = pd.DataFrame()

        if not df_xl.empty:
            # 월×시도 키로 합산: cnt 합치고 avg_pay는 가중 평균
            df_xl["cnt"]     = df_xl["cnt"].astype(int)
            df_xl["avg_pay"] = pd.to_numeric(df_xl["avg_pay"], errors="coerce")
            df_db["cnt"]     = df_db["cnt"].astype(int)
            df_db["avg_pay"] = pd.to_numeric(df_db["avg_pay"], errors="coerce")

            combined = pd.concat([df_db, df_xl], ignore_index=True)
            def _wavg(grp):
                total_cnt = grp["cnt"].sum()
                valid = grp.dropna(subset=["avg_pay"])
                if valid.empty:
                    return pd.Series({"cnt": total_cnt, "avg_pay": None})
                wav = (valid["avg_pay"] * valid["cnt"]).sum() / valid["cnt"].sum()
                return pd.Series({"cnt": total_cnt, "avg_pay": round(wav)})

            df_db = (
                combined
                .groupby(["region_sido", "reg_month"], group_keys=False)
                .apply(_wavg)
                .reset_index()
                .sort_values("reg_month")
            )

    # ── 표준 시도(17개) 외 이상값 제거 (크롤링 오류로 시군구명이 저장된 경우) ──
    _VALID_SIDOS = {"서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
                    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"}
    df_db = df_db[df_db["region_sido"].isin(_VALID_SIDOS)]

    df_db["cnt"]     = df_db["cnt"].astype(int)
    df_db["avg_pay"] = pd.to_numeric(df_db["avg_pay"], errors="coerce")
    return df_db


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
                    df_disp = df_disp.drop(
                        columns=["salary_raw", "salary_net_min", "salary_net_max", "공고링크"]
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
    display = display.drop(
        columns=["salary_raw", "salary_net_min", "salary_net_max", "recruit_count", "공고링크"]
    )
    _html = display.to_html(escape=False, index=False)
    # 진료과 ellipsis: th + td 모두 적용을 위해 style 블록 주입
    _html = _html.replace("<table ", '<table class="hosp-list-tbl" ')
    _style = (
        "<style>"
        ".hosp-list-tbl td:nth-child(4), .hosp-list-tbl th:nth-child(4) {"
        "  width:90px; max-width:90px;"
        "  overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"
        "}"
        "</style>"
    )
    for _col, _css in {
        "고용형태": "width:85px",
        "중복횟수": "width:62px",
        "등록일":   "width:74px",
    }.items():
        _html = _html.replace(f"<th>{_col}</th>", f'<th style="{_css}">{_col}</th>')
    st.markdown(_style + _html, unsafe_allow_html=True)


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
if selected_region != "전체":
    df = df[df["region"] == selected_region]
else:
    # 전체 지역일 때는 시도 단위 행만 사용 (시군 행과의 중복 카운팅 방지)
    df = df[df["region"].str.len() == 2]
if selected_specialty != "전체":
    df = df[df["specialty"] == selected_specialty]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tab2 지도 클릭 팝업 — 시도 버블 클릭 시 해당 병원 리스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@st.dialog("🏥 지역 구인 병원 리스트", width="large")
def show_map_region_dialog(sido: str, specialty: str, emp_type: str, months: list):
    spec_lbl = specialty if specialty != "전체" else "전체 진료과"
    emp_lbl  = emp_type  if emp_type  != "전체" else "전체 고용형태"
    st.markdown(
        f"**{sido}** · {spec_lbl} · {emp_lbl} · 기준월: **{' · '.join(months)}**",
        help="지도 버블 클릭 기준 — 최신 2개월 데이터",
    )
    st.divider()

    # ── DB 쿼리 ──────────────────────────────────────────────────────────────
    db_params: dict = {"_sido": sido}
    db_conds = ["rp.region_sido = :_sido"]
    for i, m in enumerate(months):
        db_params[f"_m{i}"] = m
    month_clause = " OR ".join(
        f"LEFT(rp.register_date, 7) = :_m{i}" for i in range(len(months))
    )
    db_conds.append(f"({month_clause})")

    if specialty != "전체":
        db_conds.append("rps.specialty = :_spec")
        db_params["_spec"] = specialty
        spec_join = "JOIN recruit_post_specialties rps ON rps.post_id = rp.id"
    else:
        spec_join = """LEFT JOIN (
                           SELECT post_id,
                                  STRING_AGG(specialty, '·' ORDER BY specialty) AS specialty
                           FROM   recruit_post_specialties
                           GROUP  BY post_id
                       ) rps ON rps.post_id = rp.id"""
    if emp_type != "전체":
        db_conds.append("rp.employment_type = :_emp")
        db_params["_emp"] = emp_type

    try:
        with get_engine().connect() as conn:
            df_mh = pd.read_sql(text(f"""
                SELECT
                    rp.hospital_name          AS 병원명,
                    rp.region                 AS 지역,
                    rp.employment_type        AS 고용형태,
                    rps.specialty             AS 진료과,
                    rp.salary_net_min,
                    rp.salary_net_max,
                    rp.salary_raw,
                    LEFT(rp.register_date, 7) AS 등록월,
                    rp.url                    AS 공고링크
                FROM recruit_posts rp
                {spec_join}
                WHERE {' AND '.join(db_conds)}
                ORDER BY rp.register_date DESC, rp.hospital_name
            """), conn, params=db_params)
    except Exception as e:
        st.error(f"조회 오류: {e}")
        return

    # ── 마취과: Excel 데이터 추가 ─────────────────────────────────────────────
    if specialty == "마취통증의학과":
        xl_params: dict = {"_xl_sido": f"{sido}%"}
        for i, m in enumerate(months):
            xl_params[f"_xm{i}"] = m
        xl_month_clause = " OR ".join(
            f"meh.reg_month = :_xm{i}" for i in range(len(months))
        )
        try:
            with get_engine().connect() as conn:
                df_xl_mh = pd.read_sql(text(f"""
                    SELECT
                        meh.hospital_name  AS 병원명,
                        meh.region         AS 지역,
                        '봉직의'           AS 고용형태,
                        '마취통증의학과'   AS 진료과,
                        meh.net_pay        AS salary_net_min,
                        meh.net_pay        AS salary_net_max,
                        NULL               AS salary_raw,
                        meh.reg_month      AS 등록월,
                        '[엑셀]'           AS 공고링크
                    FROM machwi_excel_history meh
                    WHERE meh.source = 'excel_import'
                      AND meh.region LIKE :_xl_sido
                      AND ({xl_month_clause})
                """), conn, params=xl_params)
        except Exception:
            df_xl_mh = pd.DataFrame()

        if not df_xl_mh.empty:
            df_mh = pd.concat([df_mh, df_xl_mh], ignore_index=True)
            df_mh = df_mh.sort_values(["등록월", "병원명"], ascending=[False, True])

    if df_mh.empty:
        st.info("해당 기간 내 공고 데이터가 없습니다.")
        return

    # ── 포맷 ─────────────────────────────────────────────────────────────────
    def _fmt_pay(row):
        mn, mx = row.get("salary_net_min"), row.get("salary_net_max")
        if pd.notna(mn) and pd.notna(mx) and float(mn) > 0:
            mn_i, mx_i = int(mn), int(mx)
            return f"{mn_i:,}" if mn_i == mx_i else f"{mn_i:,}~{mx_i:,}"
        raw = row.get("salary_raw")
        return str(raw) if pd.notna(raw) and raw else "-"

    df_mh.insert(4, "Net월급(만원)", df_mh.apply(_fmt_pay, axis=1))
    df_mh = df_mh.drop(columns=["salary_raw", "salary_net_min", "salary_net_max", "공고링크"])

    st.caption(f"총 **{len(df_mh)}건**")
    st.markdown(df_mh.to_html(escape=False, index=False), unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 화면
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.title("🏥 구인 트렌드 대시보드")
st.caption(f"필터 적용 중 → 지역: **{selected_region}** · 진료과: **{selected_specialty}**")

tab1, tab2 = st.tabs(["📋 지역 상세 분석", "🗺️ 전국 지도 & 흐름 보기"])

# 한 번의 rerun에서 다이얼로그가 두 번 열리는 것을 방지
st.session_state["_dialog_opened"] = False

EMPLOYMENT_TYPES = [
    "전체", "봉직의", "대진의", "당직의", "전임의", "전공의",
    "입원전담전문의", "출장검진", "임상(사내의사)", "임상외", "동업", "기타",
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tab 1: 지역 상세 분석 (기존 기능 전체)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab1:

    # ── 막대그래프 — 제목 + 고용형태 드롭다운 (인라인) ─────────────────────
    col_title, col_emp = st.columns([5, 2])
    with col_title:
        st.subheader("📊 월별 구인건수")
        st.caption("💡 막대를 클릭하면 해당 월의 병원 목록을 확인할 수 있습니다.")
    with col_emp:
        st.markdown("<br>", unsafe_allow_html=True)
        selected_employment = st.selectbox(
            "👔 고용형태",
            EMPLOYMENT_TYPES,
            index=EMPLOYMENT_TYPES.index("봉직의"),
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

    # ── KPI 카드 ───────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    total_posts = int(df_monthly["post_count"].sum()) if not df_monthly.empty else 0
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
            x="reg_month", y="post_count", text="post_count",
            labels={"reg_month": "등록 월", "post_count": "공고 수"},
            color_discrete_sequence=["#2196F3"],
            category_orders={"reg_month": sorted(df_monthly["reg_month"].tolist())},
        )
        fig.update_traces(
            textposition="outside", textfont_size=12,
            hovertemplate="<b>%{x}</b><br>공고 수: <b>%{y}건</b>  ← 클릭하세요<extra></extra>",
        )
        fig.update_layout(
            xaxis_title="등록 월", yaxis_title="공고 수",
            plot_bgcolor="white",
            xaxis=dict(tickangle=-30, type="category"),
            yaxis=dict(gridcolor="#eeeeee", zeroline=True,
                       range=[0, df_monthly["post_count"].max() * 1.25]),
            bargap=0.35, height=460,
            margin=dict(t=30, b=50, l=50, r=20),
            hoverlabel=dict(bgcolor="white", font_size=13),
            clickmode="event",
        )
        event = st.plotly_chart(
            fig, use_container_width=True,
            on_select="rerun", selection_mode="points", key="bar_chart",
        )
        points = event.selection.get("points", []) if event.selection else []
        current_bar_sel = str(points[0].get("x", "")) if points else ""
        if not current_bar_sel:
            st.session_state["_prev_bar_sel"] = ""
        if (current_bar_sel
                and current_bar_sel != st.session_state.get("_prev_bar_sel", "")
                and not st.session_state.get("_dialog_opened", False)):
            st.session_state["_prev_bar_sel"] = current_bar_sel
            st.session_state["_dialog_opened"] = True
            show_hospital_dialog(
                current_bar_sel, selected_region,
                selected_specialty, selected_employment,
            )

    # ── 상세 데이터 테이블 ─────────────────────────────────────────────────
    with st.expander("📋 상세 데이터 테이블 보기"):
        if df_emp.empty:
            st.info("데이터가 없습니다.")
        else:
            st.dataframe(
                df_emp.sort_values(["reg_month", "region", "specialty"])
                .rename(columns={
                    "region": "지역", "specialty": "진료과",
                    "employment_type": "고용형태",
                    "reg_month": "등록 월", "post_count": "공고 수",
                })
                .reset_index(drop=True),
                use_container_width=True, hide_index=True,
            )

    # ── 급여 현황 — 월별 Net 월급 추이 ────────────────────────────────────
    st.divider()
    st.subheader("💰 급여 현황 — 월별 평균 Net 월급 추이 (봉직의)")
    st.caption(
        "봉직의 공고 한정 · Net 월급 기준 · 인센티브 비포함 · 협의/미기재 공고 제외 · "
        "15건 이상 그룹: IQR 이상치 제거 후 평균 · 15건 미만 그룹: 중앙값"
    )

    df_sal = load_salary_monthly(selected_region, selected_specialty)

    sk1, sk2, sk3 = st.columns(3)
    if not df_sal.empty:
        total_cnt   = int(df_sal["공고수"].sum())
        overall_avg = int(
            (df_sal["평균Net월급"] * df_sal["공고수"]).sum() / df_sal["공고수"].sum()
        )
        peak = df_sal.loc[df_sal["평균Net월급"].idxmax()]
        sk1.metric("집계 공고 수",  f"{total_cnt:,}건")
        sk2.metric("전체 기간 평균", f"{overall_avg:,}만원")
        sk3.metric("최고 평균 월",  f"{peak['등록월']} ({int(peak['평균Net월급']):,}만원)")
    else:
        sk1.metric("집계 공고 수",  "-")
        sk2.metric("전체 기간 평균", "-")
        sk3.metric("최고 평균 월",  "-")

    st.divider()

    if df_sal.empty:
        st.info("선택한 조건에 해당하는 급여 데이터가 없습니다.")
    else:
        region_label    = selected_region    if selected_region    != "전체" else "전국"
        specialty_label = selected_specialty if selected_specialty != "전체" else "전체 진료과"
        fig_sal = px.bar(
            df_sal, x="등록월", y="평균Net월급",
            text=df_sal["평균Net월급"].apply(lambda v: f"{int(v):,}만원"),
            custom_data=["공고수"],
            color_discrete_sequence=["#43A047"],
            category_orders={"등록월": sorted(df_sal["등록월"].tolist())},
            title=f"{region_label} · {specialty_label} 월별 평균 Net 월급",
        )
        fig_sal.update_traces(
            textposition="outside", textfont_size=12,
            hovertemplate=(
                "<b>%{x}</b><br>평균 Net 월급: <b>%{y:,}만원</b><br>"
                "집계 공고: %{customdata[0]}건<extra></extra>"
            ),
        )
        fig_sal.update_layout(
            xaxis_title="등록 월", yaxis_title="평균 Net 월급 (만원)",
            plot_bgcolor="white",
            xaxis=dict(tickangle=-30, type="category"),
            yaxis=dict(gridcolor="#eeeeee", zeroline=True,
                       range=[max(0, df_sal["평균Net월급"].min() * 0.85),
                              df_sal["평균Net월급"].max() * 1.15]),
            bargap=0.35, height=460,
            margin=dict(t=50, b=50, l=60, r=20),
            hoverlabel=dict(bgcolor="white", font_size=13),
            title_font_size=15,
        )
        st.plotly_chart(fig_sal, use_container_width=True)

    # ── 지역별 / 진료과별 순위 expander ───────────────────────────────────
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
                    margin=dict(t=40, b=40, l=10, r=80), title_font_size=14,
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

    # ── 마취통증의학과 장기 트렌드 ────────────────────────────────────────
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
            COLOR_XLS  = "#2196F3"
            COLOR_DBC  = "#FF9800"
            ANNOT_STYLE = dict(
                xref="paper", yref="paper", showarrow=False,
                font=dict(color="red", size=12, family="Arial"),
                align="left", bgcolor="rgba(255,255,255,0.85)",
                bordercolor="red", borderwidth=1, borderpad=5,
            )

            df_plot = df_combined.copy()
            df_plot["출처"] = df_plot["출처"].replace({"엑셀(과거)": "A", "DB(크롤링)": "B"})

            # 차트 1: 공고수
            st.markdown("#### 📊 월별 구인 공고수")
            fig_cnt = px.bar(
                df_plot, x="등록월", y="공고수", color="출처",
                color_discrete_map={"A": COLOR_XLS, "B": COLOR_DBC},
                text="공고수", barmode="group",
            )
            fig_cnt.update_traces(textposition="outside")
            show_ma_cnt = st.checkbox("추세선 표시 (12개월 이동평균)", value=True, key="ma_cnt")
            if show_ma_cnt:
                _cnt_ma = (
                    df_plot.sort_values("등록월")[["등록월", "공고수"]]
                    .assign(MA=lambda d: d["공고수"].rolling(12, min_periods=3).mean().round(1))
                )
                fig_cnt.add_trace(go.Scatter(
                    x=_cnt_ma["등록월"], y=_cnt_ma["MA"],
                    mode="lines", name="추세선 (12개월 MA)",
                    line=dict(color="#000000", width=2.5),
                    hovertemplate="<b>%{x}</b><br>이동평균: <b>%{y:.1f}건</b><extra></extra>",
                ))
            fig_cnt.update_layout(
                xaxis=dict(title="등록 월", tickangle=-30, type="category",
                           categoryorder="category ascending"),
                yaxis=dict(title="공고 수", gridcolor="#eeeeee", zeroline=True),
                plot_bgcolor="white", bargap=0.25, bargroupgap=0.1, height=450,
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

            # 차트 2: 급여 추이
            st.markdown("#### 💰 월별 평균 Net 월급 추이")
            adjust_incentive = st.checkbox(
                "인센티브 보정 적용 — B에 +200만원 추가 (A와 비교 가능한 수준으로 보정)",
                value=True,
            )
            st.caption("A: 공고 기재 급여 평균 (인센티브 포함) │ B: net/monthly 공고만 집계 (인센티브 미포함)")

            df_sal_m = df_plot.dropna(subset=["평균Net월급"]).sort_values("등록월").copy()
            if adjust_incentive:
                df_sal_m.loc[df_sal_m["출처"] == "B", "평균Net월급"] += 200

            d_a = df_sal_m[df_sal_m["출처"] == "A"]
            d_b = df_sal_m[df_sal_m["출처"] == "B"]
            b_label = "B (+200 보정)" if adjust_incentive else "B"

            fig_sal2 = go.Figure()
            for d, label, color, dash in [
                (d_a, "A",      COLOR_XLS, "solid"),
                (d_b, b_label,  COLOR_DBC, "dash"),
            ]:
                if d.empty:
                    continue
                fig_sal2.add_trace(go.Scatter(
                    x=d["등록월"], y=d["평균Net월급"],
                    mode="lines+markers+text", name=label,
                    line=dict(color=color, width=2, dash=dash),
                    marker=dict(size=7),
                    text=d["평균Net월급"].apply(lambda v: f"{int(v):,}"),
                    textposition="top center",
                    textfont=dict(size=10, color=color),
                    hovertemplate=(
                        f"<b>%{{x}}</b><br>평균 Net 월급: <b>%{{y:,}}만원</b> [{label}]<extra></extra>"
                    ),
                ))

            if not d_a.empty and not d_b.empty:
                fig_sal2.add_trace(go.Scatter(
                    x=[d_a.iloc[-1]["등록월"], d_b.iloc[0]["등록월"]],
                    y=[d_a.iloc[-1]["평균Net월급"], d_b.iloc[0]["평균Net월급"]],
                    mode="lines",
                    line=dict(color="gray", width=1.5, dash="dot"),
                    showlegend=False, hoverinfo="skip",
                ))

            show_ma_sal = st.checkbox("추세선 표시 (12개월 이동평균)", value=True, key="ma_sal")
            if show_ma_sal:
                _sal_ma = (
                    df_sal_m.sort_values("등록월")[["등록월", "평균Net월급"]]
                    .assign(MA=lambda d: d["평균Net월급"].rolling(12, min_periods=3).mean().round(0))
                )
                fig_sal2.add_trace(go.Scatter(
                    x=_sal_ma["등록월"], y=_sal_ma["MA"],
                    mode="lines", name="추세선 (12개월 MA)",
                    line=dict(color="#000000", width=2.5),
                    hovertemplate="<b>%{x}</b><br>이동평균: <b>%{y:,.0f}만원</b><extra></extra>",
                ))

            all_vals = df_sal_m["평균Net월급"].tolist()
            y_min = max(0, min(all_vals) * 0.90) if all_vals else 0
            y_max = max(all_vals) * 1.12          if all_vals else 5000
            annot_sal = (
                "A: 인센티브 포함　　B: +200만원 보정 적용"
                if adjust_incentive else
                "A: 인센티브 포함(+200만원)　B: 인센티브 비포함"
            )
            fig_sal2.update_layout(
                xaxis=dict(title="등록 월", tickangle=-30, type="category",
                           categoryorder="category ascending"),
                yaxis=dict(title="평균 Net 월급 (만원)", gridcolor="#eeeeee",
                           zeroline=False, range=[y_min, y_max]),
                plot_bgcolor="white", height=460,
                margin=dict(t=20, b=60, l=60, r=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            xanchor="right", x=1),
                hoverlabel=dict(bgcolor="white", font_size=13),
            )
            fig_sal2.add_annotation(
                x=0.01, y=0.97, text=annot_sal, **ANNOT_STYLE,
            )
            st.plotly_chart(fig_sal2, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tab 2: 전국 지도 & 흐름 보기
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab2:

    if selected_specialty == "전체":
        st.info(
            "📌 **진료과를 선택하면 전국 흐름을 볼 수 있습니다.**\n\n"
            "왼쪽 사이드바에서 특정 진료과(예: 마취통증의학과, 내과 등)를 선택하세요."
        )
    else:
        # ── 고용형태 필터 (Tab2 독자) ──────────────────────────────────────
        t2_col, _ = st.columns([2, 5])
        with t2_col:
            selected_emp_t2 = st.selectbox(
                "👔 고용형태", EMPLOYMENT_TYPES, index=0, key="emp_filter_t2",
            )

        df_nat = load_national_trend(selected_specialty, selected_emp_t2)

        if df_nat.empty:
            st.warning("데이터가 없습니다. 다른 조건을 선택해 주세요.")
        else:
            sidos = sorted(df_nat["region_sido"].unique().tolist())
            COLS  = 4

            # ── 1단: 시도별 스몰 멀티플즈 ──────────────────────────────────
            st.subheader(f"📊 시도별 월별 추이 — {selected_specialty}")
            st.caption("막대 (좌측 Y): 구인 건수 · 꺾은선 (우측 Y): 평균 Net 페이 만원")

            for i in range(0, len(sidos), COLS):
                cols = st.columns(COLS)
                for j, sido in enumerate(sidos[i:i + COLS]):
                    d = df_nat[df_nat["region_sido"] == sido].sort_values("reg_month")
                    with cols[j]:
                        fig_m = go.Figure()
                        fig_m.add_trace(go.Bar(
                            x=d["reg_month"], y=d["cnt"],
                            name="건수", marker_color="#90CAF9", yaxis="y",
                            hovertemplate="%{x}<br>건수: <b>%{y}건</b><extra></extra>",
                        ))
                        d_pay = d.dropna(subset=["avg_pay"])
                        pay_max = (d_pay["avg_pay"].max() * 1.1
                                   if not d_pay.empty else 3000)
                        if not d_pay.empty:
                            fig_m.add_trace(go.Scatter(
                                x=d_pay["reg_month"], y=d_pay["avg_pay"],
                                name="평균페이", mode="lines+markers",
                                marker=dict(size=4),
                                line=dict(color="#E53935", width=1.5),
                                yaxis="y2",
                                hovertemplate="%{x}<br>페이: <b>%{y:,}만원</b><extra></extra>",
                            ))
                        fig_m.update_layout(
                            title=dict(text=sido, font=dict(size=12, color="#333"), x=0.5),
                            xaxis=dict(tickangle=-60, tickfont=dict(size=7),
                                       type="category", nticks=6, showgrid=False),
                            yaxis=dict(showgrid=True, gridcolor="#eeeeee",
                                       tickfont=dict(size=8), title=""),
                            yaxis2=dict(overlaying="y", side="right",
                                        tickfont=dict(size=8), title="", showgrid=False,
                                        range=[1300, pay_max]),
                            showlegend=False, height=200,
                            margin=dict(t=28, b=40, l=30, r=30),
                            plot_bgcolor="#fafafa",
                        )
                        st.plotly_chart(fig_m, width="stretch")

            st.divider()

            # ── 2단: 시도 선택 → 시군구별 스몰 멀티플즈 ───────────────────
            st.subheader("🔍 시도 내 시군구별 상세 추이")
            selected_sido = st.selectbox("시도 선택", sidos, key="sido_select_t2")

            df_agg_t2 = df_all.copy()
            if selected_specialty != "전체":
                df_agg_t2 = df_agg_t2[df_agg_t2["specialty"] == selected_specialty]
            if selected_emp_t2 != "전체":
                df_agg_t2 = df_agg_t2[df_agg_t2["employment_type"] == selected_emp_t2]

            sigungu_rows = df_agg_t2[
                (df_agg_t2["region"].str.len() > 2) &
                (df_agg_t2["region"].str.startswith(selected_sido))
            ]
            df_sg = (
                sigungu_rows
                .groupby(["region", "reg_month"])["post_count"].sum()
                .reset_index()
            )

            # ── 마취통증의학과 선택 시 Excel 데이터도 시군구별 건수 합산 ─────
            if selected_specialty == "마취통증의학과":
                try:
                    with get_engine().connect() as conn:
                        df_xl_sg = pd.read_sql(text("""
                            SELECT meh.region    AS region,
                                   meh.reg_month AS reg_month,
                                   COUNT(*)      AS post_count
                            FROM   machwi_excel_history meh
                            WHERE  meh.source = 'excel_import'
                              AND  meh.region LIKE :sido_like
                              AND  LENGTH(meh.region) > 2
                            GROUP  BY meh.region, meh.reg_month
                        """), conn, params={"sido_like": f"{selected_sido}%"})
                except Exception:
                    df_xl_sg = pd.DataFrame()

                if not df_xl_sg.empty:
                    df_xl_sg["post_count"] = df_xl_sg["post_count"].astype(int)
                    df_sg = pd.concat([df_sg, df_xl_sg], ignore_index=True)
                    df_sg = (
                        df_sg.groupby(["region", "reg_month"])["post_count"]
                        .sum().reset_index()
                    )

            # ── 시군구별 급여 집계 (DB) ──────────────────────────────────────
            _sg_conds = [
                "rp.region_sido = :_sido",
                "rp.salary_net_min > 1300",
                "rp.salary_net_max > 1300",
                "SPLIT_PART(rp.region, ' ', 2) ~ '(시|군)$'",
            ]
            _sg_params: dict = {"_sido": selected_sido}
            _sg_join = ""
            if selected_specialty != "전체":
                _sg_conds.append("rps.specialty = :_spec")
                _sg_params["_spec"] = selected_specialty
                _sg_join = "JOIN recruit_post_specialties rps ON rps.post_id = rp.id"
            if selected_emp_t2 != "전체":
                _sg_conds.append("rp.employment_type = :_emp")
                _sg_params["_emp"] = selected_emp_t2
            try:
                with get_engine().connect() as conn:
                    df_sg_pay = pd.read_sql(text(f"""
                        SELECT
                            (rp.region_sido || REGEXP_REPLACE(
                                SPLIT_PART(rp.region, ' ', 2), '(시|군)$', ''
                            )) AS region,
                            LEFT(rp.register_date, 7) AS reg_month,
                            ROUND(AVG((rp.salary_net_min + rp.salary_net_max) / 2.0)) AS avg_pay
                        FROM recruit_posts rp
                        {_sg_join}
                        WHERE {' AND '.join(_sg_conds)}
                        GROUP BY (rp.region_sido || REGEXP_REPLACE(
                                     SPLIT_PART(rp.region, ' ', 2), '(시|군)$', ''
                                 )),
                                 LEFT(rp.register_date, 7)
                    """), conn, params=_sg_params)
                    df_sg_pay["avg_pay"] = pd.to_numeric(df_sg_pay["avg_pay"], errors="coerce")
            except Exception:
                df_sg_pay = pd.DataFrame()

            # 마취과: Excel 급여도 시군구별 합산 (단순 평균)
            if selected_specialty == "마취통증의학과":
                try:
                    with get_engine().connect() as conn:
                        df_xl_sg_pay = pd.read_sql(text("""
                            SELECT meh.region    AS region,
                                   meh.reg_month AS reg_month,
                                   ROUND(AVG(meh.net_pay)) AS avg_pay
                            FROM   machwi_excel_history meh
                            WHERE  meh.source = 'excel_import'
                              AND  meh.region LIKE :sido_like
                              AND  LENGTH(meh.region) > 2
                            GROUP  BY meh.region, meh.reg_month
                        """), conn, params={"sido_like": f"{selected_sido}%"})
                        df_xl_sg_pay["avg_pay"] = pd.to_numeric(
                            df_xl_sg_pay["avg_pay"], errors="coerce")
                except Exception:
                    df_xl_sg_pay = pd.DataFrame()

                if not df_xl_sg_pay.empty:
                    if df_sg_pay.empty:
                        df_sg_pay = df_xl_sg_pay
                    else:
                        combined_pay = pd.concat([df_sg_pay, df_xl_sg_pay], ignore_index=True)
                        df_sg_pay = (
                            combined_pay.groupby(["region", "reg_month"])["avg_pay"]
                            .mean().round().reset_index()
                        )

            if df_sg.empty:
                st.info(f"**{selected_sido}** 내 시군구 단위 데이터가 없습니다.")
            else:
                sigungu_list = sorted(df_sg["region"].unique().tolist())
                st.caption(f"{selected_sido} 내 {len(sigungu_list)}개 시군구")
                for i in range(0, len(sigungu_list), COLS):
                    cols = st.columns(COLS)
                    for j, sg in enumerate(sigungu_list[i:i + COLS]):
                        d = df_sg[df_sg["region"] == sg].sort_values("reg_month")
                        with cols[j]:
                            fig_sg = go.Figure()
                            fig_sg.add_trace(go.Bar(
                                x=d["reg_month"], y=d["post_count"],
                                marker_color="#A5D6A7", yaxis="y",
                                hovertemplate="%{x}<br>건수: <b>%{y}건</b><extra></extra>",
                            ))
                            sg_pay_max = 3000
                            if not df_sg_pay.empty:
                                d_pay = (df_sg_pay[df_sg_pay["region"] == sg]
                                         .dropna(subset=["avg_pay"])
                                         .sort_values("reg_month"))
                                if not d_pay.empty:
                                    sg_pay_max = d_pay["avg_pay"].max() * 1.1
                                    fig_sg.add_trace(go.Scatter(
                                        x=d_pay["reg_month"], y=d_pay["avg_pay"],
                                        mode="lines+markers",
                                        marker=dict(size=4),
                                        line=dict(color="#E53935", width=1.5),
                                        yaxis="y2",
                                        hovertemplate="%{x}<br>페이: <b>%{y:,}만원</b><extra></extra>",
                                    ))
                            fig_sg.update_layout(
                                title=dict(text=sg, font=dict(size=11, color="#333"), x=0.5),
                                xaxis=dict(tickangle=-60, tickfont=dict(size=7),
                                           type="category", nticks=6, showgrid=False),
                                yaxis=dict(showgrid=True, gridcolor="#eeeeee",
                                           tickfont=dict(size=8), title=""),
                                yaxis2=dict(overlaying="y", side="right",
                                            tickfont=dict(size=8), title="", showgrid=False,
                                            range=[1300, sg_pay_max]),
                                showlegend=False, height=200,
                                margin=dict(t=26, b=38, l=25, r=30),
                                plot_bgcolor="#fafafa",
                            )
                            st.plotly_chart(fig_sg, width="stretch")

            st.divider()

            # ── 3단: 최신 2개월 버블 맵 ────────────────────────────────────
            SIDO_COORDS = {
                "서울": (37.5665, 126.9780), "부산": (35.1796, 129.0756),
                "대구": (35.8714, 128.6014), "인천": (37.4563, 126.7052),
                "광주": (35.1595, 126.8526), "대전": (36.3504, 127.3845),
                "울산": (35.5384, 129.3114), "세종": (36.4800, 127.2890),
                "경기": (37.4138, 127.5183), "강원": (37.8228, 128.1555),
                "충북": (36.8000, 127.7000), "충남": (36.5184, 126.8000),
                "전북": (35.7175, 127.1530), "전남": (34.8161, 126.4630),
                "경북": (36.4919, 128.8889), "경남": (35.4606, 128.2132),
                "제주": (33.4890, 126.4983),
            }

            all_months_nat = sorted(df_nat["reg_month"].unique().tolist())
            recent_months  = all_months_nat[-2:] if len(all_months_nat) >= 2 else all_months_nat
            month_label    = " · ".join(recent_months)

            st.subheader(f"🗺️ 최신 동향 지도 ({month_label})")
            st.caption("버블 크기 = 구인 건수 · 색상 = 평균 Net 페이 (파랑→빨강: 낮음→높음)")

            df_recent = (
                df_nat[df_nat["reg_month"].isin(recent_months)]
                .groupby("region_sido")
                .agg(cnt=("cnt", "sum"), avg_pay=("avg_pay", "mean"))
                .reset_index()
            )
            df_recent["avg_pay"] = pd.to_numeric(
                df_recent["avg_pay"], errors="coerce"
            ).round(0)
            df_recent["lat"] = df_recent["region_sido"].map(
                lambda s: SIDO_COORDS.get(s, (None, None))[0]
            )
            df_recent["lon"] = df_recent["region_sido"].map(
                lambda s: SIDO_COORDS.get(s, (None, None))[1]
            )
            df_recent = df_recent.dropna(subset=["lat", "lon"])

            if df_recent.empty:
                st.info("지도를 그릴 데이터가 없습니다.")
            else:
                cnt_min = df_recent["cnt"].min()
                cnt_max = df_recent["cnt"].max()
                if cnt_max > cnt_min:
                    df_recent["bubble_size"] = (
                        18 + (df_recent["cnt"] - cnt_min) / (cnt_max - cnt_min) * 60
                    )
                else:
                    df_recent["bubble_size"] = 38

                # 검은 테두리용 레이어 (본 버블보다 4px 크게, 검정)
                fig_map = go.Figure(go.Scattermapbox(
                    lat=df_recent["lat"],
                    lon=df_recent["lon"],
                    mode="markers",
                    marker=dict(
                        size=df_recent["bubble_size"] + 4,
                        color="black",
                        sizemode="diameter",
                        opacity=1.0,
                    ),
                    hoverinfo="skip",
                    showlegend=False,
                ))
                # 컬러 버블 레이어 (전면)
                fig_map.add_trace(go.Scattermapbox(
                    lat=df_recent["lat"],
                    lon=df_recent["lon"],
                    mode="markers+text",
                    marker=dict(
                        size=df_recent["bubble_size"],
                        color=df_recent["avg_pay"],
                        colorscale="RdYlBu_r",
                        showscale=True,
                        colorbar=dict(title="평균페이<br>(만원)", thickness=12, len=0.6),
                        sizemode="diameter",
                        opacity=0.85,
                    ),
                    text=df_recent["region_sido"],
                    textposition="top center",
                    textfont=dict(size=11, color="black"),
                    customdata=df_recent[["cnt", "avg_pay"]].fillna(0).values,
                    hovertemplate=(
                        "<b>%{text}</b><br>"
                        "구인 건수: <b>%{customdata[0]:.0f}건</b><br>"
                        "평균 Net 페이: <b>%{customdata[1]:,.0f}만원</b><extra></extra>"
                    ),
                ))
                fig_map.update_layout(
                    mapbox=dict(
                        style="carto-positron",
                        center=dict(lat=36.5, lon=127.8),
                        zoom=5.8,
                    ),
                    height=540,
                    margin=dict(t=10, b=0, l=0, r=0),
                )
                map_event = st.plotly_chart(
                    fig_map,
                    width="stretch",
                    config={"scrollZoom": True},
                    on_select="rerun",
                    key="map_chart_t2",
                )
                current_map_sel = (str(map_event.selection.points[0]["point_index"])
                                   if map_event.selection.points else "")
                if not current_map_sel:
                    st.session_state["_prev_map_sel"] = ""
                if (current_map_sel
                        and current_map_sel != st.session_state.get("_prev_map_sel", "")
                        and not st.session_state.get("_dialog_opened", False)):
                    pt = map_event.selection.points[0]
                    clicked_sido = df_recent.iloc[pt["point_index"]]["region_sido"]
                    st.session_state["_prev_map_sel"] = current_map_sel
                    st.session_state["_dialog_opened"] = True
                    show_map_region_dialog(
                        clicked_sido, selected_specialty, selected_emp_t2, recent_months
                    )

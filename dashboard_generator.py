"""
dashboard_generator.py  –  Phase 5: 멀티 필터링 시각화 시스템 + DB 스냅샷 보존형 UPSERT

공개 API
--------
init_db()                         DB 및 테이블 초기화 (최초 1회)
upsert_records(records)           크롤링 결과 저장 (스냅샷 보존형)
generate_dashboard(region, ...)   대시보드 PNG 생성

필터링 모드
----------
1) region="전체"                  → 모든 지역의 월별 공고 수를 격자(Grid) 형태로 저장
2) region="서울", specialties=[…] → 해당 지역 내 여러 과의 추이를 개별 그래프로 나열

실행
----
    python dashboard_generator.py
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

import matplotlib
matplotlib.use("Agg")           # GUI 없는 환경(서버·스케줄러)에서도 PNG 저장 가능
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib import rcParams
import pandas as pd


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 설정값
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DB_PATH      = "recruit_data.db"
OUTPUT_PNG   = "dashboard_output.png"
COLS_PER_ROW = 3       # 서브플롯 한 줄당 최대 열 수 (3 또는 4 추천)

# 색상 팔레트 (과별/지역별 구분용)
_PALETTE = [
    "#2196F3", "#E91E63", "#4CAF50", "#FF9800",
    "#9C27B0", "#00BCD4", "#FF5722", "#607D8B",
    "#795548", "#009688", "#CDDC39", "#F44336",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 한글 폰트 설정 (Windows 기본: 맑은 고딕)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _setup_korean_font() -> None:
    candidates = ["Malgun Gothic", "NanumGothic", "AppleGothic", "DejaVu Sans"]
    available  = {f.name for f in fm.fontManager.ttflist}
    for font in candidates:
        if font in available:
            rcParams["font.family"] = font
            break
    rcParams["axes.unicode_minus"] = False   # 마이너스 기호 깨짐 방지


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DB 초기화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def init_db(db_path: str = DB_PATH) -> None:
    """
    SQLite DB와 recruit_snapshots 테이블을 생성합니다.
    이미 존재하면 아무 작업도 하지 않습니다.

    스키마 설계 원칙
    ----------------
    • UNIQUE 키: (hospital_name, region, specialty, reg_month)
      → 같은 병원의 같은 지역·과·등록월 조합을 하나의 기준 레코드로 관리
    • 웹사이트에서 공고가 내려가도 DB 행은 삭제되지 않음 (스냅샷 보존)
    """
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recruit_snapshots (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                hospital_name TEXT    NOT NULL,         -- 병원명
                region        TEXT    NOT NULL,         -- 지역  (예: 서울, 경기)
                specialty     TEXT    NOT NULL,         -- 진료과 (예: 내과, 외과)
                reg_month     TEXT    NOT NULL,         -- 등록 월 YYYY-MM
                first_seen_at TEXT    NOT NULL,         -- 최초 수집 시각
                last_seen_at  TEXT    NOT NULL,         -- 최근 수집 시각
                UNIQUE(hospital_name, region, specialty, reg_month)
            )
        """)
        conn.commit()
    print(f"[DB] 초기화 완료 → {db_path}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 스냅샷 보존형 UPSERT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def upsert_records(records: list[dict], db_path: str = DB_PATH) -> None:
    """
    크롤링 결과를 DB에 저장합니다.

    동작 규칙
    ---------
    • (병원명 + 지역 + 과 + 등록 월)이 이미 존재하면 → last_seen_at 갱신
    • 새로운 조합이면 → 새 행 INSERT (과거 기록 절대 삭제 안 됨)

    Parameters
    ----------
    records : list[dict]
        필수 키: hospital_name, region, specialty, reg_month (YYYY-MM 형식)

    Examples
    --------
    upsert_records([
        {"hospital_name": "서울A병원", "region": "서울",
         "specialty": "내과", "reg_month": "2025-01"},
    ])
    """
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO recruit_snapshots
                (hospital_name, region, specialty, reg_month, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(hospital_name, region, specialty, reg_month)
            DO UPDATE SET last_seen_at = excluded.last_seen_at
            """,
            [
                (r["hospital_name"], r["region"], r["specialty"],
                 r["reg_month"], now, now)
                for r in records
            ],
        )
        conn.commit()
    print(f"[UPSERT] {len(records)}건 처리 완료 → {db_path}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 내부 헬퍼: 데이터 로드 / 보간 / 서브플롯
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _load_aggregated(db_path: str) -> pd.DataFrame:
    """DB 전체를 (region, specialty, reg_month, post_count)로 집계하여 반환."""
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT region, specialty, reg_month,
                   COUNT(*) AS post_count
            FROM   recruit_snapshots
            GROUP  BY region, specialty, reg_month
            ORDER  BY region, specialty, reg_month
            """,
            conn,
        )


def _make_series(sub: pd.DataFrame, all_months: list[str]) -> list[int]:
    """
    특정 그룹(sub)에서 all_months 순서로 공고 수를 반환.
    데이터가 없는 달은 0으로 채워 선이 끊기지 않게 보간합니다.
    """
    mapping = dict(zip(sub["reg_month"], sub["post_count"]))
    return [int(mapping.get(m, 0)) for m in all_months]


def _build_grid(n_plots: int) -> tuple:
    """n_plots개의 서브플롯 격자(fig, axes_flat)를 반환. squeeze=False로 항상 2D 보장."""
    ncols = min(COLS_PER_ROW, n_plots)
    nrows = (n_plots + ncols - 1) // ncols
    fig, axes = plt.subplots(
        nrows, ncols,
        figsize=(6 * ncols, 4 * nrows),
        squeeze=False,
    )
    return fig, axes.flatten()


def _draw_line(ax, all_months: list[str], counts: list[int],
               title: str, color: str) -> None:
    """단일 서브플롯에 월별 공고 수 선 그래프를 그립니다."""
    x = list(range(len(all_months)))
    ax.plot(x, counts, marker="o", linewidth=2.2, color=color, zorder=3)
    ax.fill_between(x, counts, alpha=0.12, color=color)

    # 각 데이터 포인트 위에 공고 수 숫자 표시
    y_max = max(counts) if counts else 1
    for xi, cnt in zip(x, counts):
        offset = y_max * 0.07 if y_max > 0 else 0.3   # 선과 겹치지 않도록 위로 올림
        ax.annotate(
            str(cnt),
            xy=(xi, cnt),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center", va="bottom",
            fontsize=9, fontweight="bold", color=color,
        )

    ax.set_title(title, fontsize=12, fontweight="bold", pad=8)
    ax.set_xlabel("등록 월", fontsize=8)
    ax.set_ylabel("공고 수",  fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(all_months, rotation=45, ha="right", fontsize=7)
    ax.set_ylim(bottom=0, top=max(counts) * 1.3 if max(counts) > 0 else 3)
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax.grid(axis="y", linestyle="--", alpha=0.4, zorder=0)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 모드 1: 지역 전체 — 모든 지역 × 월별 합계
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _plot_all_regions(df: pd.DataFrame, output_path: str) -> None:
    """
    지역 '전체' 선택 시:
    각 지역의 월별 총 공고 수를 격자 형태로 한 장의 PNG에 저장합니다.
    """
    regions    = sorted(df["region"].unique())
    all_months = sorted(df["reg_month"].unique())

    # 지역 × 월별 합산 (과 구분 없이 집계)
    region_monthly = (
        df.groupby(["region", "reg_month"])["post_count"]
        .sum()
        .reset_index()
    )

    fig, axes = _build_grid(len(regions))

    for i, region in enumerate(regions):
        sub    = region_monthly[region_monthly["region"] == region]
        counts = _make_series(sub, all_months)
        _draw_line(axes[i], all_months, counts, region, _PALETTE[i % len(_PALETTE)])

    # 남은 빈 서브플롯 숨기기
    for j in range(len(regions), len(axes)):
        axes[j].set_visible(False)

    fig.suptitle("지역별 월별 공고 수 추이 (전체)",
                 fontsize=16, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[저장] {output_path}  (전체 지역 모드 / {len(regions)}개 지역)")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 모드 2: 1개 지역 + 여러 과 — 과별 추이 개별 그래프
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _plot_region_specialties(
    df: pd.DataFrame,
    region: str,
    specialties: list[str],
    output_path: str,
) -> None:
    """
    1개 지역 + 여러 과 선택 시:
    해당 지역 내 각 과의 월별 공고 수 추이를 개별 그래프로 동시 나열합니다.
    """
    region_df = df[(df["region"] == region) & (df["specialty"].isin(specialties))]

    if region_df.empty:
        print(f"[경고] '{region}' × {specialties} 조합의 데이터가 없습니다.")
        return

    all_months = sorted(region_df["reg_month"].unique())

    fig, axes = _build_grid(len(specialties))

    for i, specialty in enumerate(specialties):
        sub    = region_df[region_df["specialty"] == specialty]
        counts = _make_series(sub, all_months)
        _draw_line(axes[i], all_months, counts, specialty, _PALETTE[i % len(_PALETTE)])

    for j in range(len(specialties), len(axes)):
        axes[j].set_visible(False)

    fig.suptitle(f"{region}  —  과별 월별 공고 수 추이",
                 fontsize=16, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[저장] {output_path}  ({region} / {specialties})")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 공개 메인 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def generate_dashboard(
    region: str = "전체",
    specialties: list[str] | None = None,
    db_path: str = DB_PATH,
    output_path: str = OUTPUT_PNG,
) -> None:
    """
    대시보드 PNG를 생성하여 저장합니다.

    Parameters
    ----------
    region : str
        "전체"       → 모든 지역의 월별 합계를 격자 형태로 표시
        특정 지역명  → 해당 지역 내 과별 추이를 개별 그래프로 표시
    specialties : list[str] | None
        선택할 과 목록. None 이면 해당 지역의 전체 과를 자동 선택.
        region="전체" 일 때는 무시됩니다.
    db_path : str
        SQLite DB 파일 경로 (기본값: recruit_data.db)
    output_path : str
        저장할 PNG 파일 경로 (기본값: dashboard_output.png)
    """
    _setup_korean_font()
    init_db(db_path)

    df = _load_aggregated(db_path)
    if df.empty:
        print("[경고] DB에 데이터가 없습니다. 크롤러를 먼저 실행한 뒤 다시 시도하세요.")
        return

    if region == "전체":
        _plot_all_regions(df, output_path)
    else:
        if specialties is None:
            specialties = sorted(
                df[df["region"] == region]["specialty"].unique().tolist()
            )
        _plot_region_specialties(df, region, specialties, output_path)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 직접 실행 시 — 샘플 데이터로 동작 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if __name__ == "__main__":
    init_db()

    # ── 테스트용 샘플 데이터 ────────────────────────────────────────────────
    sample = [
        # 서울 / 내과
        {"hospital_name": "서울A병원", "region": "서울", "specialty": "내과",   "reg_month": "2024-10"},
        {"hospital_name": "서울B병원", "region": "서울", "specialty": "내과",   "reg_month": "2024-10"},
        {"hospital_name": "서울C병원", "region": "서울", "specialty": "내과",   "reg_month": "2024-11"},
        {"hospital_name": "서울D병원", "region": "서울", "specialty": "내과",   "reg_month": "2024-12"},
        {"hospital_name": "서울E병원", "region": "서울", "specialty": "내과",   "reg_month": "2025-01"},
        {"hospital_name": "서울F병원", "region": "서울", "specialty": "내과",   "reg_month": "2025-01"},
        {"hospital_name": "서울G병원", "region": "서울", "specialty": "내과",   "reg_month": "2025-02"},
        # 서울 / 외과
        {"hospital_name": "서울A병원", "region": "서울", "specialty": "외과",   "reg_month": "2024-10"},
        {"hospital_name": "서울H병원", "region": "서울", "specialty": "외과",   "reg_month": "2024-11"},
        {"hospital_name": "서울I병원", "region": "서울", "specialty": "외과",   "reg_month": "2024-12"},
        {"hospital_name": "서울J병원", "region": "서울", "specialty": "외과",   "reg_month": "2025-01"},
        {"hospital_name": "서울K병원", "region": "서울", "specialty": "외과",   "reg_month": "2025-02"},
        # 서울 / 정형외과
        {"hospital_name": "서울L병원", "region": "서울", "specialty": "정형외과", "reg_month": "2024-11"},
        {"hospital_name": "서울M병원", "region": "서울", "specialty": "정형외과", "reg_month": "2024-12"},
        {"hospital_name": "서울N병원", "region": "서울", "specialty": "정형외과", "reg_month": "2024-12"},
        {"hospital_name": "서울O병원", "region": "서울", "specialty": "정형외과", "reg_month": "2025-01"},
        # 경기 / 내과
        {"hospital_name": "경기A병원", "region": "경기", "specialty": "내과",   "reg_month": "2024-10"},
        {"hospital_name": "경기B병원", "region": "경기", "specialty": "내과",   "reg_month": "2024-11"},
        {"hospital_name": "경기C병원", "region": "경기", "specialty": "내과",   "reg_month": "2024-11"},
        {"hospital_name": "경기D병원", "region": "경기", "specialty": "내과",   "reg_month": "2025-01"},
        # 경기 / 소아청소년과
        {"hospital_name": "경기E병원", "region": "경기", "specialty": "소아청소년과", "reg_month": "2024-10"},
        {"hospital_name": "경기F병원", "region": "경기", "specialty": "소아청소년과", "reg_month": "2024-12"},
        {"hospital_name": "경기G병원", "region": "경기", "specialty": "소아청소년과", "reg_month": "2025-01"},
        # 부산 / 내과
        {"hospital_name": "부산A병원", "region": "부산", "specialty": "내과",   "reg_month": "2024-10"},
        {"hospital_name": "부산B병원", "region": "부산", "specialty": "내과",   "reg_month": "2024-11"},
        {"hospital_name": "부산C병원", "region": "부산", "specialty": "내과",   "reg_month": "2025-01"},
        # 부산 / 피부과
        {"hospital_name": "부산D병원", "region": "부산", "specialty": "피부과", "reg_month": "2024-11"},
        {"hospital_name": "부산E병원", "region": "부산", "specialty": "피부과", "reg_month": "2024-12"},
        {"hospital_name": "부산F병원", "region": "부산", "specialty": "피부과", "reg_month": "2025-01"},
        {"hospital_name": "부산G병원", "region": "부산", "specialty": "피부과", "reg_month": "2025-02"},
    ]

    upsert_records(sample)

    # ── 모드 1: 전체 지역 격자 대시보드 ─────────────────────────────────────
    print("\n[모드 1] 전체 지역 대시보드 생성")
    generate_dashboard(
        region="전체",
        output_path="dashboard_output.png",
    )

    # ── 모드 2: 서울 + 여러 과 동시 비교 ────────────────────────────────────
    print("\n[모드 2] 서울 · 내과/외과/정형외과 대시보드 생성")
    generate_dashboard(
        region="서울",
        specialties=["내과", "외과", "정형외과"],
        output_path="dashboard_output_seoul.png",
    )

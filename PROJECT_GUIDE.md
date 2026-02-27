# 🏥 메디게이트 구인 트렌드 프로젝트 가이드

> **목적:** 이 파일은 언제 어떤 도구(Antigravity / Claude Code / Cursor)로 다시 시작하더라도
> 전체 흐름을 즉시 파악하고 이어서 작업할 수 있도록 작성된 **살아있는 문서**입니다.
> **새 작업이 완료될 때마다 반드시 업데이트하세요.**

---

## 📌 프로젝트 한 줄 요약

**메디게이트(medigate.net)의 의사 구인 공고를 크롤링 → PostgreSQL 저장 → Streamlit 대시보드로 시각화**

---

## 🗂️ 폴더 구조 및 주요 파일

```
25.크롤링(메겟)/
│
├── phase4_crawler.py      ★ 메인 크롤러 (Selenium + BeautifulSoup → PostgreSQL)
│                            목록 수집 + 신규 공고 즉시 급여 수집 통합
│                            --info / --from / --to 옵션으로 날짜 범위 지정 가능
├── salary_backfill.py     ★ 기존 DB 2,760건에 급여 데이터 추가 (상세 페이지 방문, 1회성)
├── salary_calculator.py   ★ 한국 실수령액 계산기 (2025 기준) + 급여 텍스트 파서
├── recalculate_net.py     ★ DB에 저장된 salary_net_min/max 재계산 (정책 변경 시 사용)
│
├── app.py                 ★ Streamlit 대시보드 (PostgreSQL → 시각화)
│
├── check_db.py            PostgreSQL 스키마 확인
├── db_stats.py            PostgreSQL 데이터 현황 조회 (월별/지역별/과별)
├── query_hospital.py      특정 병원 검색 및 전공과목 조회
│
├── crawl_log.txt              가장 최근 목록 크롤링 로그
├── salary_backfill_log.txt    급여 backfill 진행 로그
│
├── PROJECT_GUIDE.md       ← 지금 이 파일 (항상 최신 상태 유지)
├── PROJECT_BLUEPRINT.md   초기 기획문서 (참고용)
│
└── venv/                  Python 가상환경 (미사용, 전역 Python 사용 중)
```

---

## 🔗 핵심 연결 정보

### PostgreSQL (실제 데이터)
| 항목 | 값 |
|------|----|
| Host | `localhost` |
| Port | `5432` |
| DB명 | `medigate` |
| User | `postgres` |
| Password | `postgres` |
| Connection URL | `postgresql+psycopg2://postgres:postgres@localhost:5432/medigate` |

### 메디게이트 로그인 계정
| 항목 | 값 |
|------|----|
| ID | `bassdoctor` |
| PW | `!q2w3e4r5t` |
| 크롤링 대상 URL | `https://new.medigate.net/recruit/list` |

---

## 🗄️ DB 스키마

### `recruit_posts` — 공고 기본 정보
| 컬럼 | 설명 |
|------|------|
| `id` | PK (자동 증가) |
| `source` | `'medigate'` 또는 `'gaebigong'`(예정) |
| `post_id` | 메디게이트 공고 ID |
| `unique_key` | 중복 방지 키 = `병원명\|시도\|등록년월` |
| `hospital_name` | 병원명 |
| `hospital_type` | 병원 유형 |
| `title` | 공고 제목 |
| `employment_type` | 고용형태 |
| `region` | 전체 지역 (예: 경기 수원시 권선구) |
| `region_sido` | 시도만 (예: 경기) |
| `deadline` | 마감일 |
| `register_date` | 등록일 `YYYY-MM-DD` |
| `url` | 공고 URL |
| `is_active` | 활성 여부 |
| `crawled_at` | 수집 시각 |
| `salary_raw` | 급여 원본 텍스트 (예: "Net(세후) 월급 1,800이상~1,850미만(만원)") |
| `salary_type` | `'net'` / `'gross'` / NULL(협의·미기재) |
| `salary_unit` | `'monthly'` / `'annual'` / NULL |
| `salary_min` | 원본 최솟값 (만원) |
| `salary_max` | 원본 최댓값 (만원) |
| `salary_net_min` | **Net 환산 월급 최솟값 (만원)** ← 아래 계산 정책 참고 |
| `salary_net_max` | **Net 환산 월급 최댓값 (만원)** |
| `salary_fetched` | 상세 페이지 방문 완료 여부 (backfill 중복 방지) |

### `recruit_post_specialties` — 진료과 (1:N)
| 컬럼 | 설명 |
|------|------|
| `id` | PK |
| `post_id` | `recruit_posts.id` FK |
| `specialty` | 진료과명 (예: 내과, 가정의학과) |

---

## 💰 급여 수집 및 계산 방식

### 수집 구조
- 상세 페이지(`/recruit/{id}`) 의 **모집개요 테이블**에서 '급여' 행 파싱
- CSS: `div.my-qjvukt` → `span.my-1daa3uy`(라벨) + `div.flex-[1_0_0]`(값)

### salary_net_min / salary_net_max 계산 정책 (현행)

| 공고 유형 | 저장값 | 퇴직금 |
|----------|--------|--------|
| **Net 공고** | 공고 기재 Net 월급 그대로 (만원) | 미포함 |
| **Gross 공고** | 세후 실수령액 + Gross ÷ 12 (만원) | 포함 |
| **협의·미기재** | NULL | — |

> ⚠️ 최초 backfill(2026-02-23)에서는 Net 공고도 역산+퇴직금을 포함해 계산했으나,
> 이후 `recalculate_net.py`를 실행하여 현행 정책으로 전체 재계산 완료.

### 세금 공제 항목 (salary_calculator.py, 2025년 기준)
| 공제 항목 | 요율 | 비고 |
|----------|------|------|
| 국민연금 | 4.5% | 상한 617만원 (월 최대 277,650원) |
| 건강보험 | 3.545% | - |
| 장기요양 | 건강보험료 × 12.95% | - |
| 고용보험 | 0.9% | - |
| 소득세 | 누진세 6~45% | 근로소득공제 + 본인 기본공제 적용 |
| 지방소득세 | 소득세 × 10% | - |
| 식대 비과세 | 월 20만원 | 과세급여에서 제외 |

### 처리 규칙
- **Gross 연봉**: ÷12 로 월급 환산 후 세금 계산 + 퇴직금(Gross/12) 합산
- **Net 월급**: 공고 기재값 그대로 저장 (역산·퇴직금 없음)
- **협의/면접 후 결정/미정**: NULL 처리, 통계 제외

---

## 📊 현재 DB 데이터 현황 (2026-02-23 기준)

| 항목 | 값 |
|------|----|
| 총 데이터 | **2,760건** |
| 등록일 범위 | 2025-12-22 ~ 2026-02-18 |
| 월별 | 2025-12: 52건 / 2026-01: 1,272건 / 2026-02: 1,395건 |
| 주요 지역 | 서울 760건, 경기 754건, 인천 209건 |
| 주요 과 | 전체과 1,166건, 내과 613건, 가정의학과 497건 |
| 급여 집계 가능 공고 | **2,186건** (79.2%) / 협의 153건 / 없음 421건 |
| 전체 평균 Net 월급 | **1,921만원** (봉직의 기준, 이상치 제거 후 참고값) |
| 최고 급여 진료과 | 정형외과 2,613만원 / 신경외과 2,486만원 / 재활의학과 2,355만원 |

---

## 🔄 전체 워크플로우

```
[목록 크롤링 + 급여 통합]                      [저장]               [시각화]
phase4_crawler.py  ──────────────────────→  PostgreSQL  →→→  app.py (Streamlit)
  Selenium 로그인                             recruit_posts        월별/지역별/과별
  목록 페이지 파싱                            recruit_post_        급여 현황
  신규 공고 → 상세 페이지 방문 → 급여 파싱     specialties         병원 팝업
  중복 공고 → 스킵 (상세 방문 없음)                               구인 이력 조회
  날짜 범위 지정 가능 (--from / --to)

salary_backfill.py  →  기존 DB 보완 전용 (1회성, 이미 완료)
```

---

## 📱 대시보드 주요 기능 (app.py)

### 사이드바 필터
- **지역** (시도 + 시/군 세분화): 경기, 경기수원, 경북, 경북포항, 경남창원 등 선택 가능
  - 광역시(서울·부산·인천·대구·대전·광주·울산)는 시도 단위만 표시 (구 단위 미세분화)
- **진료과**: 선택 지역 내 존재하는 진료과만 표시

### 월별 구인건수 차트
- 고용형태 드롭다운(봉직의·대진의 등)으로 추가 필터
- 막대 클릭 → 병원 목록 팝업

### 병원 목록 팝업 (막대 클릭 시)
- **구인이력조회** (팝업 상단): 2회 이상 구인 병원 선택 → 전체 구인 이력 + 급여 이력 표시
- 병원 목록 표: 병원명 · 지역 · 고용형태 · 진료과 · **Net월급** · **중복횟수** · 등록일 · 공고링크
  - Net월급: salary_net_min~max 표시 (없으면 원본 텍스트)
  - 중복횟수: 동일 병원·지역·고용형태·**진료과** 기준 누적 구인 횟수 (2회 이상 빨간색)

### 급여 현황 — 월별 평균 Net 월급 추이 (봉직의)
- 봉직의 한정 · 사이드바 지역·진료과 필터 연동
- **이상치 처리**: 1,000만원 이하 제외 후 → 15건 이상 그룹: IQR 제거 후 평균 / 15건 미만: 중앙값

### 급여 순위 (접을 수 있는 expander)
- **지역별**: 시도 단위 수평 막대그래프 (경기는 경기 전체로 집계)
- **진료과별**: 5건 이상 진료과만 표시, 선택 지역 필터 연동

---

## ▶️ 실행 명령어

### 기존 DB 급여 backfill (1회성, 약 612분 소요 — 이미 완료)
```bash
python salary_backfill.py
# 진행 로그 → salary_backfill_log.txt (50건마다 출력)
```

### DB salary_net 재계산 (정책 변경 시 — 크롤링 없이 DB 값만으로 재계산)
```bash
python recalculate_net.py
```

### 신규 공고 수집 (목록 + 급여 통합)
```bash
# DB 현황 확인 (크롤링 없이 빠르게)
python phase4_crawler.py --info

# 날짜 범위 지정 수집 (권장 — 증분 수집)
python phase4_crawler.py --from 2026-02-19 --to 2026-02-23

# 시작일만 지정 (해당일 이후 전부)
python phase4_crawler.py --from 2026-02-19

# 전체 수집 (날짜 제한 없음)
python phase4_crawler.py

# 진행 로그 → crawl_log.txt
```

> **수집 흐름**: 신규 공고 저장 → 즉시 상세 페이지 방문 → 급여 파싱 → `salary_fetched=TRUE` 저장
> **조기 종료**: `--from` 날짜 이전 페이지가 2페이지 연속 감지되면 자동 종료
> **속도**: 신규 공고 1건당 약 3~5초 (목록 1~2초 + 상세 1.5~2.5초)

### 대시보드 실행
```bash
streamlit run app.py
# → http://localhost:8501
```

### DB 현황 확인
```bash
python phase4_crawler.py --info   # 최신일·총 건수·월별 공고 수 요약 (가장 빠름)
python db_stats.py                # 월별/지역별/과별 상세 통계
python check_db.py                # 테이블 스키마 확인
```

---

## ⚙️ 환경 설정 (최초 실행 시)

```bash
pip install selenium beautifulsoup4 psycopg2-binary
pip install streamlit plotly pandas sqlalchemy
pip install matplotlib

# Chrome + Chromedriver 필요 (Selenium용)
# PostgreSQL 서비스가 로컬에서 실행 중이어야 함
```

---

## 🐛 알려진 이슈 / 특이사항

| 이슈 | 내용 |
|------|------|
| 등록일 연도 추론 | 메디게이트는 MM/DD만 표시 → `CRAWL_YEAR`, `CURRENT_MONTH` 상수로 연도 추론. 연도 바뀔 때 수동 수정 필요 |
| 중복 키 방식 | `병원명\|시도\|등록년월` 조합. 같은 병원이 같은 달에 2개 공고 내면 1건만 저장됨 |
| 급여 파싱 정확도 | 텍스트 형식이 자유로워 일부 특수 케이스는 숫자 파싱 실패 → `salary_net = NULL` 처리 |
| Net 환산 오차 | Gross 공고의 세금 계산은 네이버 실수령액 계산기 대비 약 1~2% 오차 (식대 비과세 등 세부 가정 차이) |
| 시/군 단위 표기 | `region` 컬럼 형식: "경북 포항시 남구", "경남 창원시 의창구" 등. `SPLIT_PART(region,' ',2) ~ '(시\|군)$'` 조건으로 시/군 확인 후 `경북포항`, `경남창원` 형태로 추출. 광역시(부산·인천 등)의 구(해운대구 등)는 해당 없으므로 시도명 그대로 표시 |
| Streamlit 경고 | `use_container_width` deprecated 경고 — 동작에 무관, 추후 `width=` 파라미터로 교체 예정 |

---

## 📅 작업 이력

| 날짜 | 작업 내용 |
|------|-----------|
| 2026-02-18 | `phase4_crawler.py` 실행 → 2,760건 수집 (43분) |
| 2026-02-19 | PostgreSQL DB 현황 파악 / `app.py` Streamlit 대시보드 정상 확인 |
| 2026-02-19 | `db_stats.py`, `query_hospital.py` 작성 / `PROJECT_GUIDE.md` 최초 작성 |
| 2026-02-23 | 급여 수집 기능 설계 및 구현 |
| | — 상세 페이지 구조 파악 (`div.my-qjvukt` + `span.my-1daa3uy`) |
| | — `salary_calculator.py` 작성 (2025년 기준 실수령액 계산 + 파서) |
| | — `salary_backfill.py` 작성 후 실행 완료 (2,760건, 612분) |
| | — `recruit_posts` 테이블에 급여 컬럼 8개 추가 완료 |
| | — 급여 집계 2,186건 (79.2%) / 전체 평균 Net 1,921만원 |
| | — `app.py` 급여 섹션 추가 (지역별 / 진료과별 평균 Net 월급 차트) |
| | **대시보드 대규모 개선 (app.py)** |
| | — 급여 필터를 사이드바로 통합 (별도 드롭다운 제거) |
| | — 지역별 순위 차트: 사이드바 진료과 필터 연동 |
| | — 급여 통계 전체를 **봉직의 한정**으로 변경 |
| | — 병원 목록 팝업: Net월급 컬럼 추가 |
| | — 병원 목록 팝업: **중복횟수** 컬럼 추가 (동일 병원·지역·고용형태·진료과 기준) |
| | — 병원 목록 팝업: **구인이력조회** 섹션 추가 (팝업 최상단, 전체 급여 이력 조회) |
| | — Net 급여 계산 정책 변경: Net 공고는 공고 기재값 그대로 저장 (역산·퇴직금 없음) |
| | — `recalculate_net.py` 작성 및 실행 → 2,186건 재계산 완료 |
| | — 이상치 처리: **1,000만원 이하 제외** + IQR (≥15건: 평균 / <15건: 중앙값) |
| | — 대시보드 제목에서 '메디게이트' 제거 |
| | — 경기 세분화: 사이드바·구인건수·급여 추이에서 **경기수원·경기성남** 등 선택 가능 |
| | — 급여 순위는 시도 단위(경기 하나)로 유지 |
| | — **전 시도 시/군 세분화**: 경기 외 경북포항·경남창원 등 모든 도 지역으로 확장 |
| | — 병원 목록 팝업 지역 컬럼도 "경북포항" 형태로 표시 |
| | — 광역시(서울·부산 등)는 구 단위가 아닌 시도 그대로 유지 |
| | **`phase4_crawler.py` 급여 통합 및 날짜 범위 기능 추가** |
| | — 신규 공고 저장 즉시 상세 페이지 방문 → 급여 파싱 → 한 번에 저장 |
| | — 중복 공고는 상세 방문 없이 스킵 (속도 최적화) |
| | — `--info` 옵션: DB 현황(최신일·총 건수·월별 공고 수) 확인 후 종료 |
| | — `--from` / `--to` 옵션: 날짜 범위 지정 수집 |
| | — 범위 이전 페이지 2개 연속 감지 시 자동 조기 종료 |
| 2026-02-27 | `app.py` — 마취통증의학과 장기 트렌드 섹션 추가 (엑셀 과거자료 + DB 통합) |
| | — `load_excel_machwi()`: (마봉협)구인구직정리.xlsx 파싱 → 35개월 공고수·평균급여 추출 |
| | — `load_db_machwi()`: DB에서 마취통증의학과 월별 공고수·net/monthly 급여 집계 |
| | — 진료과 = 마취통증의학과 선택 시에만 섹션 표시 |
| | — 차트 1: 묶음 막대(엑셀=파랑 / DB=주황), 차트 2: 이중 라인 급여 추이 |
| | `PROJECT_GUIDE.md` — Supabase 이관 계획 섹션 추가 (엑셀→테이블 import 절차 포함) |

---

## 🏗️ 자체 홈페이지 연동 계획

현재 `recruit_posts.source` 컬럼으로 데이터 출처를 구분할 수 있음.

| source 값 | 의미 |
|-----------|------|
| `'medigate'` | 메디게이트 크롤링 |
| `'gaebigong'` | 자체 홈페이지 공고 (예정) |

### 홈페이지 제작 업체에 요청할 것
1. **REST API 엔드포인트** 제공 요청
   - `GET /api/recruit?page=1&updated_after=YYYY-MM-DD`
   - 반환 필드: `hospital_name`, `region`, `region_sido`, `specialties[]`, `employment_type`, `register_date`, `deadline`, `is_active`
2. **인증방식**: API Key
3. API 완성 시 → 연동 수집기(`gaebigong_crawler.py`) 별도 작성 예정

---

## ☁️ Supabase 이관 계획

로컬 PostgreSQL → Supabase(온라인 PostgreSQL)로 전환 시 아래 순서대로 진행.

### 1단계 — DB 이관 (표준 PostgreSQL 덤프)

```bash
# 로컬 → SQL 덤프
pg_dump -U postgres -d medigate -f medigate_dump.sql

# Supabase SQL 에디터 or psql로 복원
psql -h [프로젝트].supabase.co -U postgres -d postgres -f medigate_dump.sql
```

### 2단계 — app.py DB_URL 교체 (한 줄만 수정)

```python
# 변경 전
DB_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/medigate"

# 변경 후
DB_URL = "postgresql+psycopg2://postgres:[비밀번호]@[프로젝트].supabase.co:5432/postgres?sslmode=require"
```

> Supabase는 SSL 필수 → `?sslmode=require` 반드시 추가

### 3단계 — ⚠️ 엑셀 과거 데이터 이관 (놓치기 쉬움!)

**현재 상황:**
- `app.py`의 `load_excel_machwi()` 함수가 **(마봉협)구인구직정리.xlsx** 파일을 **로컬에서 직접 읽음**
- 앱을 클라우드(Streamlit Cloud 등)에 배포하면 엑셀 파일에 접근 불가 → 해당 기능 동작 안 함

**해결 방법 — 엑셀 데이터를 Supabase 테이블로 1회 import:**

```sql
-- Supabase에 테이블 생성
CREATE TABLE machwi_excel_history (
    reg_month   CHAR(7)  NOT NULL,   -- 'YYYY-MM'
    post_count  INTEGER  NOT NULL,   -- 해당 월 공고 수
    avg_net_pay INTEGER  NOT NULL,   -- 평균 Net 월급 (만원)
    PRIMARY KEY (reg_month)
);
```

import 스크립트 예시 (`import_excel_to_supabase.py` 작성 필요):

```python
# load_excel_machwi() 결과를 machwi_excel_history 테이블에 INSERT
df = load_excel_machwi()
df.rename(columns={"공고수": "post_count", "평균Net월급": "avg_net_pay", "등록월": "reg_month"})
  .drop(columns=["출처"])
  .to_sql("machwi_excel_history", engine, if_exists="replace", index=False)
```

import 완료 후 `app.py`의 `load_excel_machwi()` 함수를 아래 DB 쿼리로 교체:

```python
@st.cache_data(ttl=3600)
def load_excel_machwi() -> pd.DataFrame:
    sql = text("SELECT reg_month AS 등록월, post_count AS 공고수, avg_net_pay AS 평균Net월급 FROM machwi_excel_history ORDER BY reg_month")
    with get_engine().connect() as conn:
        df = pd.read_sql(sql, conn)
    df["출처"] = "엑셀(과거)"
    return df
```

### 이관 체크리스트

- [ ] `pg_dump`로 기존 DB 백업
- [ ] Supabase 프로젝트 생성 및 복원
- [ ] `app.py` DB_URL + `?sslmode=require` 교체
- [ ] **`machwi_excel_history` 테이블 생성 및 엑셀 데이터 import** ← 놓치지 말 것
- [ ] `load_excel_machwi()` 함수를 DB 쿼리 방식으로 교체
- [ ] `phase4_crawler.py` DB_CONFIG도 Supabase 주소로 교체

---

## 🚀 다음 작업 예정 (TODO)

- [x] `salary_backfill.py` 실행 완료 → 2,186건 급여 데이터 수집
- [x] `app.py` — 지역별/진료과별 Net 월급 비교 차트 추가
- [x] `app.py` — 급여 필터 사이드바 통합 / 봉직의 한정
- [x] `app.py` — 병원 팝업: Net월급 · 중복횟수 · 구인이력조회 추가
- [x] Net 급여 정책 수정 + `recalculate_net.py` 실행
- [x] 이상치 처리: 1,000만원 이하 제외 + IQR/중앙값
- [x] 전 시도 시/군 단위 세분화 (경기수원·경북포항·경남창원 등, 사이드바·구인건수·급여 추이·병원팝업 모두 적용)
- [x] `phase4_crawler.py` 수정 → 급여 통합 + `--info` / `--from` / `--to` 날짜 범위 옵션 추가
- [ ] `app.py` — Streamlit `use_container_width` → `width` 파라미터 교체
- [ ] 크롤러 정기 자동 실행 (Windows 작업 스케줄러)
- [ ] 마감 임박 공고 필터 기능 추가
- [ ] 지역별 히트맵 시각화 추가
- [ ] 자체 홈페이지 API 연동 크롤러(`gaebigong_crawler.py`) 작성
- [ ] **Supabase 이관 시** — `machwi_excel_history` 테이블 생성 + 엑셀 데이터 import → `load_excel_machwi()` DB 쿼리 방식으로 교체 (☁️ Supabase 이관 계획 섹션 참고)

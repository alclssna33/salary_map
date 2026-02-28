# 🏥 개원비밀공간 구인 트렌드 프로젝트 가이드

> **목적:** 이 파일은 언제 어떤 도구(Antigravity / Claude Code / Cursor)로 다시 시작하더라도
> 전체 흐름을 즉시 파악하고 이어서 작업할 수 있도록 작성된 **살아있는 문서**입니다.
> **새 작업이 완료될 때마다 반드시 업데이트하세요.**

---

## 📌 프로젝트 한 줄 요약

**메디게이트(medigate.net)의 의사 구인 공고를 크롤링 → PostgreSQL 저장 → Streamlit 대시보드로 시각화**
(서비스명: 개원비밀공간 구인 트렌드)

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
├── import_excel_to_db.py  ★ 엑셀 과거자료 → machwi_excel_history 테이블 import (1회성 완료)
│                            --reset 옵션으로 재import 가능
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

### Supabase (실제 데이터) — 2026-02-28 이관 완료
| 항목 | 값 |
|------|----|
| Host (Pooler) | `aws-1-ap-northeast-1.pooler.supabase.com` |
| Port | `5432` |
| DB명 | `postgres` |
| User | `postgres.mmqfmdqhujuohypcjkne` |
| Password | `KUHOHriqT3DdiS7w` |
| Connection URL | `postgresql+psycopg2://postgres.mmqfmdqhujuohypcjkne:KUHOHriqT3DdiS7w@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres?sslmode=require` |

> 로컬 백업: `medigate_dump.sql` (2026-02-28 덤프)

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

### `machwi_excel_history` — 마취통증의학과 엑셀 과거자료
| 컬럼 | 설명 |
|------|------|
| `id` | PK (자동 증가) |
| `reg_month` | 등록 월 `YYYY-MM` |
| `region` | 지역 (엑셀 기재값 그대로, 예: 부산, 경기수원) |
| `hospital_name` | 병원명 |
| `net_pay` | Net 월급 (만원). 예: 2300 = 2,300만원 |
| `source` | `'excel_import'` 고정 — 엑셀 수동 수집 원본임을 표시 |
| `imported_at` | import 실행 시각 |

> 원본: `(마봉협)구인구직정리.xlsx` 일자리분석 시트 / `import_excel_to_db.py`로 2026-02-27 import 완료
> 총 **4,220건** / 35개월 (2023-03 ~ 2026-01)
> Supabase 이관 시 이 테이블도 함께 이관하면 엑셀 파일 불필요

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
- **구인이력조회** (팝업 상단): 2회 이상 구인 병원 선택 → 전체 구인 이력 표(좌) + **Net월급 시계열 차트(우)** 나란히 표시
  - 차트: A(엑셀·파랑) / B(DB·주황) 출처별 라인, A-B 회색 점선 연결, 호버 툴팁
- 병원 목록 표: 병원명 · 지역 · 고용형태 · 진료과 · **Net월급** · **중복횟수** · 등록일 · 공고링크
  - Net월급: salary_net_min~max 표시 (없으면 원본 텍스트)
  - 중복횟수: 동일 병원·지역·고용형태·**진료과** 기준 누적 구인 횟수 (2회 이상 빨간색)
  - **엑셀 데이터 포함 (진료과=마취통증의학과 or 전체)**: `machwi_excel_history`의 병원도 목록에 추가
    - DB에 이미 있는 병원: 중복횟수에 Excel 누적 건수 합산
    - Excel에만 있는 병원: 새 행 추가 (진료과=마취통증의학과, 고용형태=봉직의, 공고링크=📊 엑셀 뱃지)
  - **구인이력조회**: DB 이력 + `machwi_excel_history` 이력 합산 표시 (병원명 일치 기준)

### 사이드바 필터 (개선)
- **지역·진료과 완전 독립**: 지역 변경 시 진료과 선택 유지, 진료과 변경 시 지역 선택 유지
- **검색 텍스트 입력**: 각 드롭다운 위에 검색창 — 부분 문자열 매칭으로 목록 실시간 필터
  - 예) 지역에 "경기" 입력 → 경기·경기수원·경기성남 등 표시
  - 예) 진료과에 "마취" 입력 → 마취통증의학과만 표시

### 마취통증의학과 장기 트렌드 (추가 기능)
- **지역 필터 연동**: 사이드바 지역 선택에 따라 Excel/DB 데이터 모두 필터링
- **차트 레이블**: 엑셀=A, DB=B / 빨간 주석 박스(인센티브 설명) 두 차트 모두 표시
- **인센티브 보정 체크박스** (급여 추이 차트): 체크 시 B에 +200만원 보정 · 기본 체크
- **A-B 연결선**: A 마지막 점 → B 첫 점을 회색 점선으로 연결
- **12개월 이동평균 추세선**: 검정 실선, 체크박스로 표시/숨김 (기본 표시) — 두 차트 모두
- **급여 임계값**: 1,000만원 → **1,300만원** 이하 통계 제외 (마취 DB: 650 기준 적용)

### 급여 현황 — 월별 평균 Net 월급 추이 (봉직의)
- 봉직의 한정 · 사이드바 지역·진료과 필터 연동
- **이상치 처리**: 1,000만원 이하 제외 후 → 15건 이상 그룹: IQR 제거 후 평균 / 15건 미만: 중앙값

### 급여 순위 (접을 수 있는 expander)
- **지역별**: 시도 단위 수평 막대그래프 (경기는 경기 전체로 집계)
- **진료과별**: 5건 이상 진료과만 표시, 선택 지역 필터 연동

### 탭 구조 (메인 콘텐츠)
- **Tab 1 — 지역 상세 분석**: 기존 전체 기능 (구인건수 차트, 병원 팝업, 마취 트렌드, 급여 현황, 급여 순위)
- **Tab 2 — 전국 지도 & 흐름 보기**: 특정 진료과 선택 시 활성화, 진료과=전체이면 안내 메시지 표시

### Tab 2 — 전국 지도 & 흐름 보기
- **고용형태 드롭다운**: 봉직의·대진의 등 별도 필터 (Tab 1과 독립)
- **`load_national_trend(specialty, employment_type)`**: 시도·월 기준 집계 (건수+평균페이), 마취통증의학과 선택 시 `machwi_excel_history` 합산
- **1단 — 시도별 small multiples** (4열 그리드, 높이 200px):
  - 막대(파랑, Y좌축) = 건수 / 라인(빨강, Y우축) = 평균Net월급
  - 데이터 없는 월은 건너뜀 (끊겨도 OK), 이중 Y축(`yaxis2` overlaying)
- **2단 — 시군구별 small multiples**: 시도 selectbox 선택 후 해당 시도 내 시군구별 동일 패턴
- **3단 — 전국 bubble map** (scatter_mapbox, carto-positron 무토큰):
  - 최신 2개월 데이터 기준, 버블 크기=건수, 버블 색상=평균페이(RdYlBu_r 컬러스케일)
  - 17개 시도 중심 좌표 하드코딩, 호버 툴팁 (시도명·건수·평균페이)
  - 마우스 휠 확대/축소 지원 (`config={"scrollZoom": True}`)
  - 버블 클릭 → **지역 구인 병원 리스트 팝업** (`show_map_region_dialog`): 최신 2개월 기준, 병원명·지역·고용형태·진료과·Net월급·등록월 표시 (마취과 선택 시 Excel 데이터 포함)
  - 검은 테두리 효과: 테두리용 검정 레이어 + 컬러 레이어 2중 트레이스 (Scattermapbox marker.line 미지원 우회)

### 병원 목록 팝업 (막대 클릭 시) — UI 개선
- 공고링크 컬럼 제거 (구인이력조회 테이블 및 병원 목록 표 모두)
- 진료과 열 너비 고정(90px) + 긴 내용 말줄임표(`text-overflow: ellipsis`) 처리
- 고용형태(85px) · 중복횟수(62px) · 등록일(74px) 열 너비 조정
- Tab1 고용형태 기본값 → **봉직의**

### Excel DB 데이터 품질 개선 (`machwi_excel_history`)
- DELETE: 잘못된 지역명 `경기남양`(1건) · `경기도`(19건) · `경기부천시`(1건)
- UPDATE: `경기오양`(1건) · `경기일산`(1건) → `경기고양`
- Tab 2 시도별 차트: 크롤링 오류로 저장된 비표준 시도명 제거 (표준 17개 시도만 표시)
- Tab 2 시군구별 차트: 급여 라인(빨강, 우Y축) 추가 — DB + 마취과 Excel 합산

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
| 2026-02-27 | **엑셀 과거자료 DB 이관** — `machwi_excel_history` 테이블 생성 + 4,220건 import |
| | — `import_excel_to_db.py` 작성 (--reset 옵션으로 재import 가능) |
| | — `app.py` `load_excel_machwi()` 엑셀 파일 직접 읽기 → DB 쿼리 방식으로 교체 |
| | — Supabase 이관 계획 3단계 완료 처리 (pg_dump에 자동 포함) |
| | `app.py` — 마취통증의학과 장기 트렌드 섹션 추가 (엑셀 과거자료 + DB 통합) |
| | — `load_machwi_combined(region)`: 엑셀+DB 통합, 겹치는 월 병원명 기준 중복 제거·엑셀 급여 우선, 지역 필터 지원 |
| | — 진료과 = 마취통증의학과 선택 시에만 섹션 표시 |
| | — 차트 범례 A(엑셀·인센티브 포함+200만원) / B(DB·인센티브 비포함) — 빨간색 주석 박스 |
| | — 인센티브 보정 체크박스: 체크 시 B+200만원, A-B 연결선(회색 점선) |
| | — 12개월 이동평균 추세선(검정): 공고수·급여 차트 각각 체크박스로 표시/숨김 (기본 표시) |
| | — 병원 목록 팝업: 진료과=마취/전체 시 `machwi_excel_history` 병원 포함 (중복횟수·이력 합산) |
| | — 대시보드 타이틀 변경: **메디게이트 구인 트렌드** → **개원비밀공간 구인 트렌드** |
| | — `machwi_excel_history` 병원명 정제: `$` 기호 제거(60건) + 미완성명에 `의원` 접미사 추가(2,480건) |
| | — 급여 임계값 상향: 1,000만원 → **1,300만원** (마취 DB: 650 기준) |
| | — 사이드바 필터 개선: 지역·진료과 완전 독립 + 텍스트 검색/자동완성 |
| | `PROJECT_GUIDE.md` — Supabase 이관 계획 섹션 추가 (엑셀→테이블 import 절차 포함) |
| 2026-02-28 | **신기능** — Tab 2 "전국 지도 & 흐름 보기" 추가 (`app.py` 대규모 UI 개편) |
| | — `st.tabs` 도입: Tab 1(지역 상세 분석) + Tab 2(전국 지도 & 흐름 보기) |
| | — `load_national_trend(specialty, employment_type)`: 시도·월 집계 함수 추가 (마취과 엑셀 합산 포함) |
| | — Tab 2 > 1단: 시도별 small multiples (4열, 이중Y축: 건수+평균페이, 높이200) |
| | — Tab 2 > 2단: 시도 selectbox → 시군구별 small multiples |
| | — Tab 2 > 3단: 전국 scatter_mapbox bubble map (최신 2개월, 무토큰 carto-positron) |
| | — 진료과=전체 시 Tab 2 비활성화(안내 메시지) / 특정 진료과 선택 시만 표시 |
| | — 데이터 없는 월 skip (차트 끊김 허용) |
| 2026-02-28 (2) | **Tab 2 기능 개선** |
| | — 시도별 차트: 표준 17개 시도 외 이상값(강릉·수원 등) 필터링 |
| | — 시군구별 차트: 급여 라인(빨강 우Y축) 추가 — DB + 마취과 Excel 급여 합산 |
| | — 지도 버블 클릭 → `show_map_region_dialog` 팝업 (최신 2개월 병원 리스트, 마취과 Excel 포함) |
| | — 지도 마우스 휠 확대/축소 지원 |
| | — 지도 버블 크기 확대(18~78px), 검은 테두리 효과(2중 트레이스) |
| | **Excel DB 데이터 정제** (`machwi_excel_history`) |
| | — DELETE: 경기남양(1)·경기도(19)·경기부천시(1) |
| | — UPDATE: 경기오양·경기일산 → 경기고양 |
| | **병원 목록 팝업 UI 개선** |
| | — 공고링크 컬럼 제거 (전체 팝업) |
| | — 진료과 열 90px + 말줄임표, 고용형태·중복횟수·등록일 열 너비 조정 |
| | — Tab1 고용형태 기본값 → 봉직의 |
| 2026-02-27 (2) | **버그수정** — 병원 팝업 중복횟수 집계 오류 수정 (`load_hospitals`) |
| | — 기존: 클릭된 월에 엑셀에도 등장한 DB 병원만 Excel 횟수 가산 (월 필터 버그) |
| | — 수정: 전체 기간 Excel 집계 쿼리 분리 → DB 병원에 누적 Excel 횟수 정확히 반영 |
| | — 결과: 구인이력조회 총 건수 ↔ 중복횟수 일치 (예: 삼성글로벌정형외과의원 3+7=10회) |
| | **신기능** — 구인이력조회 병원 선택 시 Net월급 시계열 차트 표시 |
| | — 이력 테이블 우측에 Plotly 라인차트 나란히 표시 (st.columns 1:1 분할) |
| | — A(엑셀, 파랑) / B(DB, 주황) 출처별 색상 구분, A-B 회색 점선 연결 |
| | — X축: 등록월, Y축: Net월급(만원) / 호버 시 월·금액 툴팁 |
| 2026-02-28 (3) | **인프라** — DB Supabase 이관 + Streamlit Community Cloud 배포 |
| | — 로컬 PostgreSQL → Supabase 이관 완료 (psql pooler 방식) |
| | — `app.py` DB_URL → `st.secrets["DB_URL"]`로 교체 (보안) |
| | — `phase4_crawler.py` DB_CONFIG Supabase 주소로 교체 |
| | — `requirements.txt` · `.gitignore` · `.streamlit/secrets.toml` 추가 |
| | — GitHub 저장소 생성 (`alclssna33/salary_map`) → main 브랜치 push |
| | — Streamlit Community Cloud 배포 완료 |
| | **버그수정** — Tab1·Tab2 다이얼로그 중복 오픈 오류 수정 |
| | — Tab1 막대 클릭 + Tab2 지도 클릭이 동시에 살아있을 때 `@st.dialog` 충돌 발생 |
| | — `_dialog_opened` 세션 플래그로 rerun당 하나의 다이얼로그만 열리도록 처리 |
| | — 크롤러 신규 수집: 379건 추가 (2026-02-24 ~ 2026-02-28) |
| 2026-02-28 (4) | **버그수정** — 월별 구인건수 카운팅 기준 통일 |
| | — 상단 `load_aggregated()`: `COUNT(DISTINCT id)` → `COUNT(DISTINCT hospital_name)` |
| | — 하단 마취 장기트렌드 `load_machwi_combined()`: DB 쿼리에 `employment_type='봉직의'` 필터 추가 |
| | — 지역=전체 시 UNION ALL 이중 카운팅 제거: 시도 단위 행(2글자)만 사용하도록 필터 추가 |
| | — 결과: 2월(DB only 월)부터 상단·하단 건수 일치 / 1월은 하단에 엑셀 합산으로 의도적 차이 유지 |
| | **버그수정** — Tab2 시도별/시군구별 급여 Y축 최솟값 1,300만원 고정 |
| | — `range=[1300, None]` 방식이 Plotly에서 미동작 → `range=[1300, data_max×1.1]` 명시적 계산으로 변경 |
| | — 시도별 small multiples · 시군구별 small multiples 모두 적용 |
| | **버그수정** — 마취 장기트렌드 시군구 선택 시 엑셀 지역 필터 오류 수정 |
| | — 경기화성 등 시군구 선택 시 엑셀 데이터가 `경기%` (경기 전체)로 필터되던 문제 수정 |
| | — `경기화성%` 형태로 정확히 필터하도록 변경 (`xl_params["xl_region"] = region`) |
| | **버그수정** — 체크박스 토글 시 병원 팝업 재오픈 방지 |
| | — 추세선·인센티브 체크박스 토글 → rerun 시 이전 차트 선택 상태가 남아 팝업 반복 오픈되던 문제 |
| | — `_prev_bar_sel` / `_prev_map_sel` 로 마지막 선택값 추적 → 값이 변경될 때만 팝업 열도록 수정 |
| | — 같은 막대/버블 재클릭: 한 번 클릭해 선택 해제 후 다시 클릭하면 팝업 열림 |
| | **신기능** — 병원 목록 팝업 중복횟수 정렬 버튼 추가 |
| | — 표 위에 오름차순 ↑ / 내림차순 ↓ 라디오 버튼 추가 (`recruit_count` 기준 정렬) |
| | — 기본값: 내림차순 (중복횟수 많은 순) |

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

## ☁️ Supabase + Streamlit Cloud 배포 현황 ✅ 완료 (2026-02-28)

### 현재 운영 구조

```
phase4_crawler.py (로컬 PC 실행)
        ↓ 직접 저장
    Supabase (온라인 PostgreSQL)
        ↓ 조회
    app.py → Streamlit Community Cloud (온라인 대시보드)
```

### 연결 방식 (Pooler, sslmode=require)

- `app.py`: `DB_URL = st.secrets["DB_URL"]` — Streamlit Cloud secrets에 등록
- `phase4_crawler.py`: `DB_CONFIG` dict에 Supabase pooler 주소 직접 입력
- 로컬 `streamlit run app.py`: `.streamlit/secrets.toml` (gitignore 처리)

### GitHub 저장소

- URL: `https://github.com/alclssna33/salary_map`
- Branch: `main`
- 배포 파일: `app.py` / `requirements.txt`

### 이관 체크리스트 ✅ 전부 완료

- [x] `pg_dump`로 기존 DB 백업 (`machwi_excel_history` 자동 포함) → `medigate_dump.sql`
- [x] Supabase 프로젝트 생성 및 psql로 복원 (2026-02-28)
- [x] `app.py` DB_URL → `st.secrets["DB_URL"]`로 교체
- [x] `phase4_crawler.py` DB_CONFIG Supabase 주소로 교체
- [x] Streamlit Community Cloud 배포 완료

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
- [x] **Tab 2 전국 지도 & 흐름 보기** — small multiples + bubble map 추가
- [x] **엑셀 과거자료 DB 이관** — `machwi_excel_history` 테이블 생성 + 4,220건 import 완료
- [x] **Supabase 이관** — 로컬 PostgreSQL → Supabase 완료 (2026-02-28)
- [x] **Streamlit Community Cloud 배포** — `alclssna33/salary_map` (2026-02-28)
- [ ] `app.py` — Streamlit `use_container_width` → `width` 파라미터 교체
- [ ] 크롤러 정기 자동 실행 (Windows 작업 스케줄러)
- [ ] 마감 임박 공고 필터 기능 추가
- [ ] 지역별 히트맵 시각화 추가
- [ ] 자체 홈페이지 API 연동 크롤러(`gaebigong_crawler.py`) 작성

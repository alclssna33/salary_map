# 프로젝트: 메디게이트 초빙정보 데이터 파이프라인 및 트렌드 분석

## 1. 프로젝트 목적
- 메디게이트(Medigate) 초빙정보 게시판 데이터를 수집하여 의사 구인구직 시장의 트렌드 분석.
- 개비공 커뮤니티 회원들에게 지역별/전공별 구인 수요 데이터를 그래프로 제공.
- 향후 제작될 자체 홈페이지의 구인구직 데이터와 통합 가능한 확장성 확보.

## 2. 핵심 기술 스택
- **Scraper:** Antigravity (프레임워크), Playwright/BeautifulSoup (엔진)
- **Editor & Architect:** Cursor (전체 구조 설계 및 UI 구현)
- **Runtime Agent:** Claude Code (CLI 기반 테스트, 디버깅, 라이브러리 관리)
- **Database:** PostgreSQL (추천) 또는 MySQL (확장성 고려)
- **Analysis:** Pandas, Plotly/Streamlit (시각화)

## 3. 단계별 실행 계획 (Roadmap)

### Phase 0: 구조 분석 (Site Discovery) - [현재 단계]
- **목표:** 메디게이트 초빙정보 페이지의 HTML 구조 및 데이터 로딩 방식 파악.
- **도구별 역할:**
    - **Cursor:** `@Web` 기능을 사용하여 `https://new.medigate.net/recruit`의 소스 코드를 분석하고 주요 데이터 필드의 CSS Selector/XPath 추출.
    - **Claude Code:** 터미널에서 `curl` 또는 간단한 파이썬 스크립트를 실행하여 서버 응답(SSR vs CSR) 및 차단 정책(robots.txt) 확인.
    - **Antigravity:** 분석된 구조를 바탕으로 초기 크롤링 워크플로우(Flow) 정의.

### Phase 1: DB 스키마 설계 (Architecture)
- **목표:** 메디게이트 데이터와 자체 데이터를 모두 수용하는 통합 테이블 설계.
- **필수 필드:** `source(medigate/internal)`, `post_id`, `specialty_code`, `region_code`, `salary`, `reg_date`, `is_active`.
- **도구별 역할:** Cursor를 통해 SQLAlchemy 모델링 및 ERD 설계.

### Phase 2: 크롤러 엔진 개발 (Scraper Development)
- **목표:** Antigravity 기반의 안정적인 수집기 구축.
- **핵심 로직:** 중복 제거(UPSERT), 페이지네이션 처리, 속도 제한(Rate Limiting).
- **도구별 역할:** Claude Code를 사용하여 크롤링 세션 테스트 및 에러 디버깅.

### Phase 3: 데이터 표준화 및 시각화 (Analysis & UI)
- **목표:** 수집된 비정형 데이터를 정제하여 그래프 대시보드 구현.
- **도구별 역할:** Cursor를 통해 Streamlit 기반의 트렌드 분석 리포트 페이지 작성.

---

## 4. 특이사항 및 주의사항
- **데이터 통합:** 자체 홈페이지 구축 시 구인 데이터와 메디게이트 데이터를 `specialty_code`와 `region_code` 기준으로 조인(Join)할 수 있어야 함.
- **차단 방지:** User-Agent 로테이션 및 접속 간격 랜덤화 적용.
- **확장성:** 향후 API 서버(FastAPI 등)로 전환하기 용이하도록 모듈화된 코드 작성.
# anime_downloader 플러그인 구조 분석

## 📌 개요

FlaskFarm용 **애니메이션 다운로드 플러그인**으로, 여러 애니메이션 스트리밍 사이트에서 콘텐츠를 검색하고 다운로드할 수 있는 기능을 제공합니다.

---

## 🏗️ 전체 구조

```
anime_downloader/
├── __init__.py           # 플러그인 초기화 (현재 비활성화됨)
├── setup.py              # 플러그인 설정 및 메뉴 구조, 모듈 로드
├── info.yaml             # 플러그인 메타데이터 (이름, 버전, 개발자)
├── mod_ohli24.py         # 애니24 사이트 모듈 (1,542줄)
├── mod_anilife.py        # 애니라이프 사이트 모듈 (1,322줄)
├── mod_linkkf.py         # 링크애니 사이트 모듈 (1,449줄)
├── lib/                  # 공용 라이브러리
│   ├── crawler.py        # 웹 크롤링 엔진 (Playwright, Selenium, Cloudscraper)
│   ├── ffmpeg_queue_v1.py# FFmpeg 다운로드 큐 관리
│   ├── util.py           # 유틸리티 함수 (파일명 정리, 타이밍 등)
│   └── misc.py           # 비동기 실행 헬퍼 함수
├── templates/            # HTML 템플릿 (18개 파일)
├── static/               # CSS, JS, 이미지 리소스
├── bin/                  # 플랫폼별 바이너리 (Darwin, Linux)
├── nest_api/             # 애니 API 관련 (서브디렉토리)
└── yommi_api/            # 커스텀 API 관련
```

---

## 🔧 핵심 컴포넌트

### 1. setup.py - 플러그인 엔트리포인트

| 항목 | 설명 |
|------|------|
| `__menu` | 3개 사이트별 서브메뉴 (설정, 요청, 큐, 검색, 목록) |
| `setting` | DB 사용, 기본 설정, 홈 모듈(`ohli24`) 지정 |
| `P` | FlaskFarm 플러그인 인스턴스 생성 |
| 모듈 로드 | `LogicOhli24`, `LogicAniLife`, `LogicLinkkf` |

### 2. 사이트 모듈 (mod_*.py)

각 모듈은 동일한 구조를 따릅니다:

| 클래스 | 역할 |
|--------|------|
| `LogicXxx` | 사이트별 비즈니스 로직 (검색, 시리즈 정보, 다운로드 추가) |
| `XxxQueueEntity` | 다운로드 큐 항목 (에피소드 정보, 상태 관리) |
| `ModelXxxItem` | SQLAlchemy DB 모델 (다운로드 기록 저장) |

**LogicXxx 주요 메서드:**

- `process_menu()` / `process_ajax()` - 웹 요청 처리
- `get_series_info()` - 시리즈/에피소드 정보 파싱
- `get_anime_info()` / `get_search_result()` - 목록/검색
- `add()` - 다운로드 큐에 추가
- `scheduler_function()` - 자동 다운로드 스케줄러
- `plugin_load()` / `plugin_unload()` - 생명주기 관리

### 3. lib/crawler.py - 웹 크롤링 엔진

| 메서드 | 기술 |
|--------|------|
| `get_html_requests()` | 기본 requests 요청 |
| `get_html_playwright()` | Playwright 비동기 (헤드리스 브라우저) |
| `get_html_playwright_sync()` | Playwright 동기 |
| `get_html_selenium()` | Selenium WebDriver |
| `get_html_cloudflare()` | Cloudscraper (CF 우회) |

### 4. lib/ffmpeg_queue_v1.py - 다운로드 큐

| 클래스 | 역할 |
|--------|------|
| `FfmpegQueueEntity` | 개별 다운로드 항목 (URL, 파일경로, 상태) |
| `FfmpegQueue` | 큐 관리자 (스레드 기반 다운로드, 동시 다운로드 수 제어) |

---

## 🖥️ 지원 사이트 (3개)

| 모듈 | 사이트 | URI |
|------|--------|-----|
| `mod_ohli24.py` | 애니24 (ohli24) | `/ohli24` |
| `mod_anilife.py` | 애니라이프 | `/anilife` |
| `mod_linkkf.py` | 링크애니 | `/linkkf` |

---

## 📄 템플릿 구조

각 사이트별로 6개 템플릿 제공:

- `*_setting.html` - 사이트 설정
- `*_request.html` - 다운로드 요청 페이지
- `*_queue.html` - 다운로드 큐 현황
- `*_search.html` - 검색 인터페이스
- `*_list.html` - 다운로드 목록
- `*_category.html` - 카테고리 탐색

---

## 🔄 동작 흐름

```mermaid
graph LR
    A[사용자] --> B[검색/탐색]
    B --> C[시리즈 선택]
    C --> D[에피소드 선택]
    D --> E[다운로드 큐 추가]
    E --> F[FfmpegQueue]
    F --> G[FFmpeg 다운로드]
    G --> H[DB 기록 저장]
```

---

## ⚠️ 주의사항

1. **개발 모드**: `setup.py`에서 `DEFINE_DEV = True`로 설정되어 직접 모듈 import
2. **`__init__.py` 비활성화**: 현재 주석 처리되어 `setup.py`가 실제 엔트리포인트 역할
3. **크롤링 기술 혼용**: Cloudflare 우회를 위해 Playwright, Selenium, cloudscraper 등 다양한 기술 사용

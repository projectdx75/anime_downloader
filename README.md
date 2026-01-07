# Anime Downloader for FlaskFarm

**Anime Downloader**는 FlaskFarm 플랫폼에서 동작하는 애니메이션 자동 다운로드 플러그인입니다.
국내 주요 스트리밍 사이트(Ohli24, Linkkf, Anilife)를 지원하며, 강력한 보안 우회 기능을 탑재하여 안정적인 다운로드를 보장합니다.

---

## 🚀 주요 기능 (Key Features)

*   **다중 사이트 지원**: Ohli24, Anilife, Linkkf 등 다양한 소스에서 영상 검색 및 다운로드.
*   **강력한 우회 기술 (Anti-Bot Bypass)**:
    *   **TLS Fingerprint 변조**: `curl_cffi`를 사용하여 실제 Chrome 브라우저처럼 위장, Cloudflare 및 각종 봇 차단을 무력화합니다.
    *   **CDN 자동 감지**: 스트리밍 서버(CDN)의 도메인이 수시로 변경되더라도 자동으로 감지하여 대응합니다. (예: 14B 가짜 파일 문제 해결)
*   **스마트 다운로드 큐**: `ffmpeg` 및 `yt-dlp` 기반의 큐 시스템으로 안정적인 이어받기 및 재시도를 지원합니다.
*   **사용자 편의성 및 보안**:
    *   **보안 스트리밍 (Secure Streaming)**: 외부 플레이어(MXPlayer, VLC 등) 연동 시 API 키를 노출하지 않고 **임시 스트리밍 토큰(5분 만료)**을 발급하여 안전한 시청 환경을 제공합니다.
    *   **범용 플레이어 연동**: IINA, PotPlayer, VLC, nPlayer, Infuse, MX Player 등 8종 이상의 외부 플레이어와 정교한 URL Scheme/Intent 연동을 지원합니다.
    *   **Proxy 설정**: IP 차단 시 손쉽게 우회할 수 있도록 웹 설정 UI에서 프록시 서버를 지정할 수 있습니다.
    *   **모듈형 테마 시스템**: CSS 변수와 동적 로딩을 활용하여 데스크탑/모바일 모두에 최적화된 사이트별 테마를 제공합니다.
    *   **실시간 피드백**: 다운로드 상태, 중복 파일 감지 등을 실시간 알림으로 제공합니다.

---

## 📺 지원 사이트 (Supported Sites)

### 1. Ohli24 (애니24)
*   **특징**: 강력한 인프라와 다양한 라이브러리.
*   **기술**: `Zendriver`(Daemon모드) 및 `Camoufox`를 이용한 브라우저 에뮬레이션 우회.
*   **기능**: 검색, 목록 조회, 자동 다운로드, **임시 토큰 기반 보안 스트리밍**.

### 2. Linkkf (링크애니)
*   **특징**: 빠른 업데이트 속도.
*   **기능**: 검색 및 다운로드.

### 3. Anilife (애니라이프)
*   **특징**: 다양한 화질 제공.
*   **기술**: Playwright 등을 활용한 브라우저 에뮬레이션(필요 시).

---

## 🛠 설치 및 문제 해결 (Troubleshooting)

### 필수 요구 사항

*   **Python 패키지 (Dependencies)**:
    *   `curl_cffi`: TLS Fingerprint 변조를 통한 Cloudflare 및 보안 사이트 우회용.
    *   `Zendriver`: 가벼운 브라우저 데몬 모드를 통한 고속 크롤링 지원.
    *   `Camoufox`: 강력한 안티봇 탐지 우회를 위한 고보안 브라우저 에뮬레이터.
    *   `yt-dlp`: 스트리밍 영상(HLS/DASH) 다운로드 핵심 엔진.
    *   기타: `requests`, `lxml`, `beautifulsoup4`, `flask-login` 등.
*   **시스템 도구 (System Tools)**:
    *   **ffmpeg**: 영상/음성 병합 및 **자막 합침** 기능을 위한 필수 도구 (시스템 PATH 등록 필요).
    *   **Browser (Chrome/Chromium)**: Zendriver 및 Camoufox 구동을 위한 브라우저 환경 필요.

### 자주 묻는 질문 (FAQ)

#### Q1. 설정 페이지 접근 시 404 오류가 뜹니다.
*   **원인**: 플러그인 초기화 파일(`plugin.py`)이 누락되었기 때문입니다.
*   **해결**: `plugin.py` 파일이 존재하는지 확인하고, 없다면 복구 후 서버를 재시작하세요.

#### Q2. 검색 시 결과가 없거나 "Document is empty" 오류가 발생합니다.
*   **원인**: 사이트의 보안 정책에 의해 접속이 차단된 경우입니다.
*   **해결**:
    1.  최신 버전으로 업데이트하세요. (`curl_cffi` 적용 버전)
    2.  설정 페이지에서 **Proxy URL**을 비워두거나, 작동하는 유효한 프록시 IP를 입력하세요.

#### Q3. 다운로드된 파일 용량이 매우 작습니다 (14 Byte 등).
*   **원인**: CDN 서버에서 봇 접근을 감지하고 가짜 파일을 보낸 것입니다.
*   **해결**: 플러그인 자체적으로 이를 감지하고 우회하는 패치가 적용되었습니다. 최신 버전 사용 시 자동으로 해결됩니다.

---

## ⚙️ 설정 가이드

1.  **FlaskFarm 웹 > 플러그인 > Anime Downloader > 설정**으로 이동합니다.
2.  **Proxy URL**: 필요한 경우 `http://IP:PORT` 형식으로 입력 (기본값: 공란).
3.  **저장 경로**: 다운로드된 파일이 저장될 경로 설정.
4.  **다운로드 방법**: `yt-dlp` (기본) 추천.

---

## 📝 변경 이력 (Changelog)

### v0.6.13 (2026-01-07)
- **초기화 순서 오류 수정**: `P.logger` 접근 전 `P` 인스턴스 생성이 완료되도록 `curl_cffi` 자동 설치 루틴 위치 조정 (`NameError: name 'P' is not defined` 해결)

### v0.6.11 (2026-01-07)
- **Docker 환경 최적화**:
    - `curl_cffi` 라이브러리 부재 시 자동 설치(pip install) 루틴 추가
    - URL 추출 실패 시 GDM 위임 중단 및 에러 처리 강화
- **Ohli24 GDM 연동 버그 수정**:
    - `LogicOhli24.add` 메서드의 인덴트 오류 및 문법 오류 해결
    - 다운로드 완료 시 Ohli24 DB 자동 업데이트 로직 안정화
    - `__init__.py` 안정성 강화 (P.logic 지연 로딩 대응)
- **Anilife GDM 연동**:
    - `ModuleQueue` 연동으로 Anilife 다운로드가 GDM (Gommi Downloader Manager)으로 통합
    - Ohli24와 동일한 패턴으로 `source_type: "anilife"` 메타데이터 포함
    - Go FFMPEG 버튼 → **Go GDM** 버튼으로 변경 및 GDM 큐 페이지로 링크
- **파일명 정리 개선**:
    - `Util.change_text_for_use_filename()` 함수에서 연속 점(`..`) → 단일 점(`.`) 변환
    - 끝에 오는 점/공백 자동 제거로 Synology NAS에서 Windows 8.3 단축 파일명 생성 방지
- **Git 워크플로우 개선**:
    - GitHub + Gitea 양방향 동시 푸시 설정 (GitHub 우선)

### v0.5.3 (2026-01-04)
- **보안 스트리밍 토큰 시스템 도입**:
    - 외부 플레이어 연동 시 API 키 노출 방지를 위한 **임시 토큰(TTL 5분)** 발급 로직 구현
    - 인증 없이 접근 가능한 `/normal/` 라우트를 통한 보안 스트리밍 엔드포인트 추가
- **외부 플레이어 연동 고도화**:
    - **VLC Android 지원**: `vlc://` 대신 Android Intent 형식을 적용하여 재생 오류 해결
    - **MXPlayer 최적화**: MIME 타입 명시 및 한글 파일명 URL 인코딩 안정화 (RFC 5987 대응)
- **모바일 UI/UX 미세 조정**:
    - 외부 플레이어 아이콘 오버플로우 수정 (모바일에서 두 줄로 자동 줄바꿈)
    - 비디오 플레이어 모달 내 영상 세로 중앙 정렬 보강
    - 다운로드 목록 페이지(`list`)의 카드 여백 최적화 (`p-4` → `p-3`)
- **버그 수정**:
    - `Content-Disposition` 헤더의 한글 파일명 유니코드 오류 해결

### v0.5.2 (2026-01-04)
- **재사용 가능한 비디오 모달 컴포넌트 도입**:
    - `templates/anime_downloader/components/video_modal.html` - 공통 모달 HTML
    - `static/js/video_modal.js` - VideoModal JavaScript 모듈
    - `static/css/video_modal.css` - 비디오 모달 전용 스타일시트
- **Alist 스타일 UI 개선**:
    - **에피소드 드롭다운**: 파란색 하이라이트 배경의 에피소드 선택기
    - **자동 다음 토글 스위치**: iOS 스타일 슬라이더 토글
    - **외부 플레이어 버튼**: IINA, PotPlayer, VLC, nPlayer, Infuse, OmniPlayer, MX Player, MPV 지원
- **코드 재사용성 향상**:
    - Ohli24 list 페이지에서 인라인 코드 ~145줄 → ~9줄로 축소
    - `VideoModal.init()` API로 간편 초기화 및 `openWithPlaylist()` 메서드 지원

### v0.5.1 (2026-01-04)
- **Ohli24 레이아웃 표준화**:
    - 모든 Ohli24 페이지(Setting, Search, Queue, List, Request)에 일관된 1400px max-width 및 중앙 정렬 적용
    - `ohli24.css`에 공통 wrapper(`.ohli24-common-wrapper`) 및 헤더 스타일 추가
    - List/Queue 페이지 `visible` 클래스 누락 수정 (content-cloak 트리거 추가)
    - Request 페이지 에피소드 카드 순차 렌더링 문제 해결 (`requestAnimationFrame` 사용)
- **Anilife 폴백 체인 개선**:
    - `get_html` 함수에 **Zendriver subprocess 폴백** 추가 (Daemon 실패 시 자동 전환)
    - Playwright 폴백을 **Camoufox**로 변경 (더 강력한 안티봇 우회)
    - 3단계 폴백: Zendriver Daemon → Zendriver Subprocess → Camoufox
- **Anilife 반응형 레이아웃**:
    - Request 페이지에 `anilife-common-wrapper` 클래스 적용
    - 모바일(`<992px`): 100% 너비 / 데스크탑(`≥992px`): 1400px max-width
- **Linkkf CSS 준비**:
    - `linkkf.css`에 공통 wrapper 스타일 추가 (향후 레이아웃 표준화 대비)

### v0.5.0 (2026-01-03)
- **Ohli24 비디오 플레이어 UI 전면 개편**:
    - **프리미엄 글래스모피즘 디자인**: 플레이어 모달 및 플레이리스트 컨트롤에 투명 유리 테마 적용
    - **Video.js 8.10.0 업그레이드**: 최신 엔진으로 안정성 및 재생 성능 최적화
    - **"Scale to Fill" (줌) 기능**: 모바일 전체화면 시 검은 여백을 없애고 화면을 가득 채우는 기능 추가
    - **중앙 재생 버튼 개선**: 모바일에 최적화된 대형 중앙 재생 버튼 및 아이콘 정렬 수정
- **Anilife / Ohli24 검색 엔진 고도화**:
    - **Zendriver Daemon 최적화**: 매 요청마다 브라우저를 띄우지 않고 백그라운드 프로세스 활용 (응답 속도 2~3초로 단축)
    - **완결 카테고리 & 년도별 필터링**: Ohli24 검색에 '완결' 버튼 추가 및 년도별(2020~2025) 상세 필터링 지원
    - **모던 로딩 UI**: 시각적으로 세련된 멀티 링 프리로더 및 글래스모피즘 AJAX 스피너 도입
- **Python 3.14 및 최신 스택 지원**:
    - Flask 3.1.2, SQLAlchemy 2.0.45 등 최신 라이브러리 호환성 확보 및 `AssertionError` 경고 제거
- **안정성 및 UX 강화**:
    - **Enter 키 검색**: 모든 분석/검색 페이지에서 Enter 키 지원
    - **Zendriver 자동 설치**: 환경에 패키지가 없을 경우 실행 시 자동 설치
    - **타입 힌트 리팩토링**: `mod_ohli24.py`, `mod_anilife.py` 전반에 엄격한 타입 힌트 적용

### v0.4.18 (2026-01-03)
- **Ohli24 4단계 폴백 체인 구현**: `curl_cffi` → `cloudscraper` → `Zendriver` → `Camoufox`
- **현재 전략**: 가볍고 빠른 `Zendriver`와 풀 브라우저 `Camoufox` 조합으로 클라우드플레어 완전 우회


### v0.4.17 (2026-01-02)
- **Ohli24 디자인 고도화 (전반적 UI 개선)**:
    - **썸네일 에피소드 배지**: 이미지 좌측 상단에 글래스모피즘 스타일의 세련된 에피소드 번호 배지(앰버 컬러) 추가
    - **액션 버튼 디자인**: 목록 페이지 버튼("작품보기", "보기", "삭제" 등)을 미니멀한 `.btn-minimal` 디자인으로 개편
    - **모바일 UX 최적화**: 모바일에서 "보기"(블루), "삭제"(레드) 버튼에 선명한 색상을 부여하여 가독성 및 조작성 증대
    - **데스크탑 레이아웃**: 시작/완료 날짜와 액션 버튼 사이의 간격을 대폭 늘려(Horizontal Separation) 시각적 균형 확보
    - **인터렉션**: 호버 효과 및 블루 그래디언트 강조로 프리미엄 피드백 제공


### v0.4.15 (2026-01-02)
- **Ohli24 날짜 표시 및 디자인 개선**:
    - 요청일(시작) 및 완료일 배지에 색상 구분 적용 (Slate/Green) 및 "시작:", "완료:" 라벨 추가
    - 모바일 뷰에서 날짜 배지가 카드 내부에 깔끔하게 스택되도록 레이아웃 최적화
- **Ohli24 검색 UI 모바일 최적화**:
    - 모바일 화면에서 검색 필터(정렬, 옵션) 및 버튼의 크기를 줄여 공간 효율성 증대
    - 검색창과 버튼 배치를 모바일에 맞게 2단 레이아웃으로 조정

### v0.4.13 (2026-01-02)
- **Ohli24 CSS 사이드 이펙트 수정**:
    - 페이지별 독립 wrapper (`.ohli24-list-page`, `.ohli24-request-page`, `.ohli24-queue-page`) 적용으로 스타일 간섭 완전 차단
    - 요청(Request) 페이지의 에피소드 카드 가로 정렬 레이아웃 복구 및 최적화
    - 요청 페이지 내 불필요한 인라인 스타일 제거 및 외부 CSS로 일원화
- **안정성 강화**:
    - **Ohli24**: 큐 추가 시 즉시 메타데이터 파싱 및 DB 동기화 로직 강화
    - **FfmpegQueue**: 로컬 파일 존재 시 DB 상태 동기화 누락 수정
    - **검색**: Ohli24 검색 결과 유효성 체크 로직 추가로 런타임 오류 방지
- **모듈 검색 지원**: `model_base.py` 내 Ohli24 및 Linkkf 전용 검색 지원 추가

### v0.4.5 (2026-01-02)
- **CSS 테마 아키텍처 전면 개편**:
    - 사이트별 독립 테마 파일 분리 (`anilife.css`, `linkkf.css`, `ohli24.css`)
    - 공통 모바일 로직 및 알림 스타일을 `mobile_custom.css`로 통합 (중복 코드 ~2,000줄 제거)
    - Jinja2 템플릿을 활용한 테마 동적 로딩 시스템 구현
- **백엔드 안정성 및 UX 강화**:
    - **Anilife**: `get_series_info` 파싱 로직 개선으로 `IndexError` 방지 및 크롤링 안정성 확보
    - **중복 다운로드 알림**: 이미 파일이 존재하거나 DB에 기록이 있을 경우 사용자에게 명확한 알림 메시지 출력
    - **CSS 호환성**: `line-clamp` 속성 크로스 브라우저 호환성 패치 적용

### v0.4.3 (2026-01-02)
- **모바일 UX 대폭 개선**:
    - 시스템 알림(bootstrap-notify) 커스텀 스타일링 (사이트별 테마 색상 적용)
    - Anilife: Cosmic Violet / Linkkf: Forest Green / Ohli24: Slate Blue
    - 모바일에서 상단 nav-pills 메뉴가 가려지는 문제 수정 (margin-top 50px)
    - List 페이지 검색/초기화 버튼 사이즈 최적화
    - DOM 요소 오버플로우 방지 및 컨텐츠 정렬 개선
- **다운로더 쓰레드 설정**:
    - `anilife_download_threads` 설정 추가 (yt-dlp concurrent-fragments)
    - Linkkf `get_downloader`에서 `linkkf_download_threads` 설정 반영

### v0.4.0 (2026-01-02)
- **Discord 알림 개선**:
    - 다운로드 완료 시에만 알림 전송 (시작 시 알림 제거)
    - 알림 메시지에 포스터 이미지 및 파일명 포함
- **DB 매핑 개선**:
    - 다운로드 시작 즉시 메타데이터(제목, 에피소드 번호, 화질 등) DB 동기화
    - `download_completed`에서 모든 필드 정확히 매핑
- **UI/UX 개선**:
    - Ohli24 목록에 에피소드 번호 배지 추가 (고대비 노란색)
    - Linkkf 목록에 **"자막합침"** 버튼 추가 (ffmpeg로 SRT 자막 MP4에 삽입)
- **Linkkf 다운로드 수정**:
    - `get_downloader` 메서드 추가 및 설정 페이지의 다운로드 방식 반영
    - `prepare_extra` URL 덮어쓰기 버그 수정
    - yt-dlp Fragment 파일 자동 정리
- **로그 최적화**:
    - yt-dlp 진행률 로그 빈도 감소 (10회당 1회)
    - 중복 로그 제거 (`download_completed` 단일 호출)

### v0.3.7 (2026-01-01)
- **설정 페이지 폴더 탐색 기능 추가**:
    - Ohli24, Anilife, Linkkf 모든 설정 페이지에 **폴더 탐색 버튼** 적용
    - 저장 폴더 옆 "탐색" 버튼 클릭 시 **모달 폴더 브라우저** 팝업
    - `..` (상위 폴더), `.` (현재 폴더) 네비게이션 지원
    - 더블클릭으로 하위 폴더 진입, 클릭으로 선택
    - 최소/최대 높이 설정으로 일관된 UI 제공 (min-height: 300px, max-height: 600px)

### v0.3.3 (2026-01-01)
- **Ohli24 Play 버튼 구현**:
    - 요청 페이지에서 파일이 존재할 경우 즉시 재생 가능한 "Play" 버튼 추가
    - VideoJS 기반의 비디오 플레이어 및 플레이리스트 UI 적용 (Linkkf와 동일한 UX 제공)
    - 백그라운드 파일 감지 로직 개선 (파일명의 해상도 부분 등을 glob 패턴으로 유연하게 매칭)
- **모바일 UI 최적화**:
    - Ohli24 요청 페이지에서 모바일 상단 메뉴가 컨텐츠를 가리는 현상 수정 (CSS 미디어 쿼리 적용)
- **Linkkf 리팩토링 및 개선**:
    - 카테고리 데이터 소스를 API 기반(`singlefilter.php`)으로 전면 전환하여 안정성 확보
    - "완결" 버튼 제거 및 "방영중" 버튼 클릭 시 "Anime List" 로드되도록 변경
    - 검색창 및 버튼 UI 디자인 개선 (높이 조정, 정렬 수정, "Elegant" 스타일 적용)
    - "Top" 카테고리를 내부 API 연동으로 전환하여 정확도 향상

### v0.3.0 (2025-12-31)
- **VideoJS 플레이리스트**: 비디오 플레이어에서 다음 에피소드 자동 재생
- **플레이리스트 UI**: 이전/다음 버튼, 에피소드 목록 토글
- **실시간 갱신**: 플레이어 열려있을 때 10초마다 새 에피소드 감지 및 알림

### v0.2.2 (2025-12-31)
- **해상도 자동 감지**: m3u8 master playlist에서 해상도(1080p/720p 등)를 파싱하여 파일명에 반영
- **Discord 알림 개선**: 큰 썸네일 이미지, Discord Blurple 색상, ISO 타임스탬프 적용
- **Queue 페이지 UI**: 좌우 여백을 다른 페이지들과 일치하도록 수정
- **Pre-commit hook**: 커밋 시 info.yaml 버전 자동 증가 (patch 버전)

### v0.2.1 (2025-12-30)
- **CDN 보안 우회**: cdndania.com 쿠키 기반 인증 처리 (`curl_cffi` 세션 유지)
- **CdndaniaDownloader**: 별도 프로세스 기반 HLS 세그먼트 다운로더 추가
- **프록시 지원 강화**: 세그먼트 다운로드 시 프록시 적용


# Asmama 크롤러

Playwright 기반의 고성능 웹 크롤러로 [Asmama](http://www.asmama.com) 웹사이트에서 제품 데이터를 수집하여 Excel 파일로 저장합니다.

## 🎯 프로젝트 개요

이 프로젝트는 `http://www.asmama.com/shop/shopdetail.html?branduid={branduid}` 형식의 URL에서 제품 정보를 크롤링하는 전문 도구입니다.

### 주요 특징

- **🚀 고성능**: Playwright를 활용한 안정적인 크롤링
- **🛡️ 안티봇 대응**: 랜덤 User-Agent, 지연시간, 동시 세션 제어
- **📊 Excel 저장**: 즉시 Excel 파일로 결과 저장 (PostgreSQL 호환 스키마)
- **🔍 완전한 로깅**: 성공/실패 모든 과정을 JSON 형태로 기록
- **🧪 테스트 완비**: 단위/통합 테스트 및 개발자 플레이그라운드
- **⚡ CLI 자동화**: Makefile을 통한 원클릭 실행

### 수집 데이터

| 필드 | 타입 | 설명 |
|------|------|------|
| `branduid` | string | 제품 고유 식별자 |
| `name` | string | 제품명 |
| `price` | int | 가격 (원화) |
| `options` | string[] | 제품 옵션 배열 |
| `image_urls` | string[] | 이미지 URL 배열 |
| `detail_html` | string | 상세 페이지 HTML |

## 🚀 빠른 시작

### 1. 설치 (10분 완료)

```bash
# 저장소 클론
git clone <repository-url>
cd asmama_crawling

# 의존성 설치 및 브라우저 설정
make install

# 설치 확인
make help
```

### 2. 기본 사용법

```bash
# 특정 제품 크롤링
make crawl-custom BRANDUID=1234567

# 기본 제품 크롤링 (테스트용)
make crawl

# 리스트 페이지에서 여러 제품 크롤링
make crawl-list
```

### 3. 결과 확인

```bash
# 크롤링 결과 통계
make stats

# 최근 로그 확인
make logs

# 데이터 파일 위치
ls -la data/asmama_products.xlsx
```

## 📋 상세 사용법

### CLI 명령어

#### 단일 제품 크롤링
```bash
python main.py --branduid=1234567 --output=data/my_products.xlsx
```

#### 리스트 페이지 크롤링
```bash
python main.py --list-url="http://www.asmama.com/shop/list.html" --max-items=30
```

#### 사용 가능한 옵션
- `--branduid`: 크롤링할 제품의 branduid (단일 제품)
- `--list-url`: 제품 목록 페이지 URL (다중 제품)
- `--max-items`: 최대 크롤링 아이템 수 (기본: 30)
- `--output`: 출력 파일 경로 (기본: data/asmama_products.xlsx)

### Makefile 명령어

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `make install` | 의존성 설치 | `make install` |
| `make crawl` | 기본 크롤링 실행 | `make crawl` |
| `make crawl-custom` | 사용자 지정 크롤링 | `make crawl-custom BRANDUID=1234567` |
| `make crawl-list` | 리스트 페이지 크롤링 | `make crawl-list` |
| `make test` | 전체 테스트 실행 | `make test` |
| `make test-unit` | 단위 테스트만 | `make test-unit` |
| `make clean` | 임시 파일 정리 | `make clean` |
| `make stats` | 크롤링 통계 | `make stats` |
| `make logs` | 최근 로그 보기 | `make logs` |

## 🏗️ 프로젝트 구조

```
asmama_crawling/
├── 📁 crawler/              # 핵심 크롤링 로직
│   ├── base.py             #   베이스 크롤러 클래스
│   ├── asmama.py           #   Asmama 전용 크롤러
│   ├── storage.py          #   데이터 저장소 (Excel/JSON)
│   └── utils.py            #   유틸리티 함수
├── 📁 playground/           # 개발자 테스트 도구
│   ├── test_crawler.py     #   크롤러 기본 테스트
│   ├── test_selectors.py   #   CSS 셀렉터 검증
│   ├── analyze_data.py     #   결과 데이터 분석
│   └── debug_session.py    #   디버깅 세션
├── 📁 tests/               # 테스트 코드
│   ├── test_utils.py       #   유틸리티 테스트
│   ├── test_storage.py     #   저장소 테스트
│   └── test_integration.py #   통합 테스트
├── 📁 data/                # 크롤링 결과 (자동 생성)
├── 📁 logs/                # 로그 파일 (자동 생성)
├── main.py                 # 메인 실행 파일
├── Makefile               # CLI 자동화
├── requirements.txt       # 의존성 목록
└── README.md             # 이 파일
```

### 핵심 컴포넌트

#### 1. 크롤러 계층 구조
```python
BaseCrawler          # 추상 베이스 클래스
    ↓
AsmamaCrawler       # Asmama 전용 구현체
```

#### 2. 저장소 인터페이스
```python
BaseStorage         # 추상 저장소 인터페이스
    ↓
ExcelStorage       # Excel 파일 저장
JSONStorage        # JSON 파일 저장 (개발용)
```

## 🧪 개발자 도구

### 플레이그라운드 스크립트

개발 및 디버깅을 위한 독립 실행 가능한 도구들:

```bash
# 크롤러 기본 기능 테스트
python playground/test_crawler.py --branduid=1234567

# CSS 셀렉터 검증
python playground/test_selectors.py --branduid=1234567

# 크롤링 결과 분석
python playground/analyze_data.py --input=data/asmama_products.xlsx

# 단계별 디버깅
python playground/debug_session.py --branduid=1234567 --verbose
```

### 테스트 실행

```bash
# 전체 테스트
make test

# 단위 테스트만
make test-unit

# 통합 테스트만
make test-integration

# 특정 테스트
pytest tests/test_crawler.py -v
```

## ⚙️ 설정 및 커스터마이징

### 환경 변수

```bash
# 로그 레벨 설정
export LOG_LEVEL=DEBUG

# 데이터베이스 연결 (향후 PostgreSQL 지원)
export DATABASE_URL=postgresql://localhost/asmama
```

### 설정 파일 수정

`config.py`에서 다음 항목들을 조정할 수 있습니다:

```python
# 크롤링 설정
USER_AGENT = "Mozilla/5.0 ..."
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 5

# 안티봇 대응
RANDOM_DELAY_MIN = 1.0
RANDOM_DELAY_MAX = 3.0
MAX_CONCURRENT_SESSIONS = 3
```

## 🛡️ 안티봇 대응

이 크롤러는 다음과 같은 안티봇 대응 기능을 포함합니다:

- **랜덤 User-Agent**: 5개의 실제 브라우저 User-Agent 중 랜덤 선택
- **랜덤 Viewport**: 다양한 화면 해상도 시뮬레이션
- **지연 시간**: 1-3초 랜덤 지연으로 자연스러운 패턴 구현
- **동시 세션 제한**: 최대 3개 세션으로 서버 부담 최소화
- **쿠키 재사용**: 브라우저 컨텍스트 유지로 로그인 상태 보존

## 📊 로깅 및 모니터링

### 로그 파일 구조

```
logs/
├── crawl_20240101_120000.log    # 일반 실행 로그
├── crawl_20240101_120001.log    # 타임스탬프별 분리
└── ...
```

### 로그 형식

**성공 로그**:
```
2024-01-01 12:00:00 - AsmamaCrawler - INFO - 제품 크롤링 성공: 1234567
```

**실패 로그 (JSON)**:
```json
{
  "branduid": "1234567",
  "reason": "페이지 로드 실패",
  "trace": "Traceback...",
  "timestamp": "2024-01-01T12:00:00"
}
```

### 모니터링 명령어

```bash
# 실시간 로그 보기
tail -f logs/crawl_*.log

# 에러만 필터링
grep "ERROR" logs/crawl_*.log

# 성공률 계산
grep -c "크롤링 성공" logs/crawl_*.log
```

## 🔧 트러블슈팅

### 일반적인 문제

#### 1. 브라우저 설치 문제
```bash
# Playwright 브라우저 재설치
python -m playwright install chromium

# 시스템 의존성 설치 (Ubuntu/Debian)
sudo apt-get install libnss3 libatk-bridge2.0-0 libdrm2
```

#### 2. 권한 문제
```bash
# 로그 디렉토리 권한 설정
chmod 755 logs/
chmod 755 data/

# 사용자 권한으로 설치
pip install --user -r requirements.txt
```

#### 3. 메모리 부족
```bash
# 동시 세션 수 줄이기
export MAX_WORKERS=1

# 또는 config.py에서 수정
MAX_CONCURRENT_SESSIONS = 1
```

#### 4. 네트워크 타임아웃
```bash
# 타임아웃 시간 증가
export REQUEST_TIMEOUT=60
```

### 디버깅 가이드

1. **기본 연결 확인**
   ```bash
   python playground/test_crawler.py --init-test
   ```

2. **셀렉터 검증**
   ```bash
   python playground/test_selectors.py --branduid=1234567
   ```

3. **단계별 디버깅**
   ```bash
   python playground/debug_session.py --branduid=1234567 --headless=false
   ```

4. **로그 분석**
   ```bash
   python playground/analyze_data.py --input="logs/*.log"
   ```

## 📈 성능 최적화

### 권장 설정

- **메모리**: 최소 4GB RAM
- **동시 세션**: 3개 이하 (기본값)
- **네트워크**: 안정적인 인터넷 연결
- **저장소**: 결과 파일용 충분한 디스크 공간

### 성능 모니터링

```bash
# 크롤링 통계 확인
make stats

# 시스템 리소스 모니터링
htop  # 또는 Activity Monitor (macOS)
```

## 🔮 향후 확장 계획

- [ ] PostgreSQL 데이터베이스 지원
- [ ] 웹 UI 대시보드
- [ ] 스케줄링 기능 (cron 통합)
- [ ] 다중 사이트 지원
- [ ] API 서버 모드
- [ ] 클라우드 배포 지원

## ⚖️ 라이선스 및 주의사항

### 사용 제한사항

1. **교육 및 연구 목적**으로만 사용
2. **상업적 이용** 전 해당 웹사이트 이용약관 확인
3. **과도한 요청** 지양 (서버 부담 최소화)
4. **개인정보 보호** 관련 법규 준수

### 면책사항

이 도구는 교육 목적으로 제작되었으며, 사용자는 관련 법규와 웹사이트 이용약관을 준수할 책임이 있습니다.

## 📞 지원 및 문의

- **이슈 리포트**: GitHub Issues 탭 이용
- **기능 요청**: Pull Request 환영
- **문서 개선**: README 수정 PR 제출

---
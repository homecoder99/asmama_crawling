# Asmama → Qoo10 업로드 데이터 변환 시스템

Asmama 웹사이트에서 크롤링한 상품 데이터를 Qoo10 판매자센터 업로드 형식으로 자동 변환하는 시스템입니다.

## 🚀 주요 기능

### 1. 템플릿 기반 데이터 로딩
- **금지 브랜드/경고 키워드**: `ban/ban.xlsx`
- **브랜드 매핑**: `brand/brand.csv` 
- **카테고리 매핑**: `category/Qoo10_CategoryInfo.csv`
- **기등록 상품**: `registered/registered.xlsx`
- **업로드 형식**: `upload/sample.xlsx` (48개 필드)

### 2. 이미지 품질 검사 (OpenAI Vision API)
- 쿠팡 상품 이미지 규칙 8개 항목 자동 검사
- 대표 이미지 자동 선정 (최고 점수 이미지)
- 규칙 미달 이미지 자동 필터링

### 3. 지능형 상품 필터링
- **금지 브랜드**: 완전 제거
- **경고 키워드**: AI로 상품명 자동 수정 (제거하지 않음)
- **기등록 상품**: unique_item_id 기준 중복 제거
- **대표 이미지**: 필수 검증

### 4. 자동 필드 변환
- **번역**: 한국어 → 일본어 (OpenAI GPT-4o-mini)
- **가격 변환**: 원화 → 엔화 (1원 = 0.11엔)
- **카테고리 매핑**: 키워드 기반 주얼리 카테고리 자동 분류
- **브랜드 매핑**: ASMAMA = 112630 (고정값)
- **옵션 변환**: 가격 포함 엔화 변환

### 5. Excel 출력
- Qoo10 48개 필드 형식 준수
- 18개 필수 필드 자동 채움
- 타임스탬프 기반 파일명 자동 생성

## 📁 프로젝트 구조

```
uploader/
├── src/                     # 소스 코드
│   ├── data_loader.py      # 템플릿 파일 로딩
│   ├── image_processor.py  # 이미지 품질 검사
│   ├── product_filter.py   # 상품 필터링
│   ├── field_transformer.py # 필드 변환
│   └── uploader.py         # 메인 업로더 시스템
├── templates/              # 템플릿 파일들 (사용자 제공)
│   ├── ban/ban.xlsx
│   ├── brand/brand.csv
│   ├── category/Qoo10_CategoryInfo.csv
│   ├── registered/registered.xlsx
│   └── upload/sample.xlsx
├── data/                   # 입력 데이터
├── output/                 # 출력 파일
├── logs/                   # 로그 파일
├── main.py                 # 실행 스크립트
├── test_uploader.py        # 테스트 스크립트
└── requirements.txt        # 의존성
```

## ⚙️ 설치 및 설정

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정
`.env` 파일 생성:
```bash
OPENAI_API_KEY=your_openai_api_key_here
```

### 3. 템플릿 파일 준비
`templates/` 디렉토리에 다음 파일들을 배치:
- `ban/ban.xlsx`: 금지 브랜드/경고 키워드
- `brand/brand.csv`: 브랜드 번호 매핑  
- `category/Qoo10_CategoryInfo.csv`: 카테고리 번호 매핑
- `registered/registered.xlsx`: 기등록 상품 목록
- `upload/sample.xlsx`: Qoo10 업로드 형식 (48개 필드)

## 🎯 사용법

### 기본 사용법
```bash
python main.py --input data/asmama_products.xlsx
```

### 고급 옵션
```bash
python main.py \
  --input data/crawled_data.json \
  --templates custom_templates \
  --output results \
  --log-level DEBUG
```

### 매개변수 설명
- `--input`: 크롤링된 데이터 파일 (Excel/JSON)
- `--templates`: 템플릿 파일 디렉토리 (기본값: templates)
- `--output`: 출력 디렉토리 (기본값: output)
- `--log-level`: 로그 레벨 (DEBUG/INFO/WARNING/ERROR)

## 🧪 테스트

테스트 스크립트 실행:
```bash
python test_uploader.py
```

테스트 과정:
1. 샘플 크롤링 데이터 생성
2. 전체 변환 프로세스 실행
3. 결과 검증 및 리포트 생성

## 📊 데이터 플로우

```
크롤링 데이터 (Excel/JSON)
        ↓
1. 템플릿 파일 로딩
        ↓
2. 이미지 품질 검사 (OpenAI Vision)
        ↓
3. 상품 필터링 (금지브랜드, 경고키워드, 기등록상품)
        ↓
4. 필드 변환 (번역, 가격변환, 카테고리매핑)
        ↓
5. Excel 출력 (Qoo10 48개 필드 형식)
        ↓
Qoo10 업로드 파일 + 처리 리포트
```

## 📈 처리 통계

시스템은 각 단계별 처리 통계를 제공합니다:

- **입력 상품 수**: 원본 크롤링 데이터 개수
- **이미지 처리 완료**: 이미지 품질 검사 완료 상품
- **필터링 통과**: 모든 필터링 조건 통과 상품
- **필드 변환 완료**: 번역 및 변환 완료 상품
- **최종 출력**: Excel 파일 출력 상품
- **전체 성공률**: 입력 대비 최종 출력 비율

## 🔧 카테고리 매핑

주얼리 카테고리 키워드 자동 매핑:

| 카테고리 번호 | 카테고리명 | 키워드 |
|--------------|-----------|--------|
| 300002342 | 목걸이 | 목걸이, 체인, 펜던트 |
| 320001121 | 반지 | 반지, 링 |
| 320001451 | 발찌 | 발찌 |
| 320001452 | 팔찌 | 팔찌 |
| 300000000 | 귀걸이 | 귀걸이, 이어링, 피어싱 |
| 300000001 | 브로치 | 브로치, 핀 |
| 300000002 | 헤어액세서리 | 헤어핀, 헤어끈, 헤어밴드 |

## 🛡️ 이미지 품질 규칙

OpenAI Vision API로 검사하는 쿠팡 이미지 8개 규칙:

1. **크기**: 상품이 이미지 짧은 변의 80% 이상
2. **텍스트**: 추가된 텍스트/워터마크 금지
3. **중앙 배치**: 상품이 이미지 중앙에 위치
4. **배경**: 흰색 또는 거의 흰색 배경
5. **구성**: 판매 단위에 포함된 항목만 표시
6. **단일 촬영**: 콜라주나 합성 금지
7. **사은품 제외**: 무료 증정품 표시 금지
8. **정면 촬영**: 상품의 정면 모습 (±15도)

## 💰 가격 변환

한국 원화를 일본 엔화로 자동 변환:
- **환율**: 1원 = 0.11엔 (약 1,100원 = 100엔)
- **상품 가격**: 자동 변환 후 10엔 단위 절사
- **옵션 가격**: 추가 가격도 엔화로 변환

## 📝 로그 및 리포트

### 로그 파일
- 위치: `logs/uploader.log`
- 형식: 타임스탬프, 모듈명, 레벨, 메시지
- 성공/실패 상품별 상세 로그

### 처리 리포트
- 위치: `output/processing_report_[timestamp].txt`
- 내용: 전체 통계, 필터링 상세, 변환 결과
- 제거/수정된 상품 예시 포함

## 🔄 워크플로 예시

```bash
# 1. 크롤링 데이터 준비
# data/asmama_products.xlsx (500개 상품)

# 2. 변환 실행
python main.py --input data/asmama_products.xlsx

# 3. 결과 확인
# output/qoo10_upload_20241225_143022.xlsx (387개 상품)
# output/processing_report_20241225_143022.txt

# 4. 통계 예시
# 입력: 500개 → 최종: 387개 (성공률 77.4%)
# 제거: 113개 (이미지 부족 45개, 기등록 68개)
# 수정: 23개 (경고 키워드 수정)
```

## 🚨 주의사항

### API 사용량
- **OpenAI Vision API**: 이미지당 약 0.01-0.02달러
- **OpenAI GPT API**: 번역당 약 0.001달러
- 상품 수에 따른 API 비용 고려 필요

### 처리 시간
- 상품당 평균 5-10초 (이미지 검사 포함)
- 100개 상품 기준 약 10-15분 소요
- 네트워크 상태 및 이미지 크기에 따라 변동

### 메모리 사용량
- 대용량 파일 처리 시 메모리 사용량 증가
- 1,000개 이상 상품 처리 시 배치 단위 처리 권장

## 🛠️ 트러블슈팅

### OpenAI API 오류
```
APIError: Rate limit exceeded
→ API 요청 제한 초과, 잠시 후 재시도
```

### 메모리 부족
```
MemoryError: Unable to allocate array
→ 입력 파일을 작은 단위로 분할 처리
```

### 템플릿 파일 오류
```
FileNotFoundError: templates/ban/ban.xlsx
→ 템플릿 파일 경로 및 존재 여부 확인
```

## 📞 지원

문제 발생 시:
1. 로그 파일 확인 (`logs/uploader.log`)
2. 처리 리포트 검토 (`output/processing_report_*.txt`)
3. 테스트 스크립트 실행 (`python test_uploader.py`)

---

🎯 **목표**: Asmama 크롤링 데이터를 Qoo10에서 바로 업로드 가능한 형식으로 완벽 변환
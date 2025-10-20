.PHONY: help install oliveyoung-crawl oliveyoung-upload asmama-crawl upload-celeb validate-celeb

# Default goal
.DEFAULT_GOAL := help

# Variables
PYTHON := source .venv/bin/activate && python
PIP := source .venv/bin/activate && uv pip
DATA_DIR := data
UPLOADER_DIR := uploader
TEMPLATES_DIR := $(UPLOADER_DIR)/templates
OUTPUT_DIR := $(UPLOADER_DIR)/output

help: ## 사용 가능한 명령어를 표시합니다
	@echo "크롤러 - 사용 가능한 명령어:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "예시:"
	@echo "  make install                    # 의존성 설치"
	@echo "  make oliveyoung-crawl MAX_ITEMS=5 OUTPUT_FILENAME=my_test.xlsx  # Oliveyoung 크롤링"
	@echo "  make oliveyoung-upload INPUT_FILE=data/file.xlsx  # Oliveyoung 업로드 변환"
	@echo "  make asmama-crawl LIST_URL=\"http://example.com\"  # Asmama 크롤링"
	@echo "  make upload-celeb               # 셀럽 검증된 데이터를 Qoo10 업로드 변환"
	@echo "  make validate-celeb             # 셀럽 정보 필수로 데이터 검증"

install: ## 의존성을 설치합니다
	@echo "의존성 설치 중..."
	uv venv .venv
	$(PIP) install -r requirements.txt
	$(PYTHON) -m playwright install chromium
	@echo "의존성 설치 완료!"

oliveyoung-crawl: ## Oliveyoung 크롤링을 실행합니다 (MAX_ITEMS=1, OUTPUT_FILENAME 조절 가능)
	@if [ -z "$(MAX_ITEMS)" ]; then \
		MAX_ITEMS=1; \
	fi; \
	if [ -z "$(OUTPUT_FILENAME)" ]; then \
		OUTPUT_FILENAME="oliveyoung_products_0812.xlsx"; \
	fi; \
	echo "Oliveyoung 크롤링 시작: $$MAX_ITEMS개 상품, 출력파일: $$OUTPUT_FILENAME"; \
	uv run playground/test_oliveyoung_crawler.py --test-filter --use-excel --max-items=$$MAX_ITEMS --output-filename=$$OUTPUT_FILENAME

oliveyoung-crawl-new: ## Oliveyoung 최신 상품만 크롤링합니다 (EXISTING_EXCEL, MAX_ITEMS, OUTPUT_FILENAME 조절 가능)
	@if [ -z "$(EXISTING_EXCEL)" ]; then \
		EXISTING_EXCEL="data/oliveyoung_20250929.xlsx"; \
	fi; \
	if [ -z "$(MAX_ITEMS)" ]; then \
		MAX_ITEMS=15; \
	fi; \
	if [ -z "$(OUTPUT_FILENAME)" ]; then \
		OUTPUT_FILENAME="oliveyoung_new_products.xlsx"; \
	fi; \
	echo "Oliveyoung 최신 상품 크롤링 시작"; \
	echo "  - 기존 데이터: $$EXISTING_EXCEL"; \
	echo "  - 카테고리당 최대: $$MAX_ITEMS개"; \
	echo "  - 출력 파일: $$OUTPUT_FILENAME"; \
	uv run playground/test_oliveyoung_crawler.py --test-new-products --existing-excel=$$EXISTING_EXCEL --max-items=$$MAX_ITEMS --use-excel --output-filename=$$OUTPUT_FILENAME

oliveyoung-upload: ## Oliveyoung 크롤링 데이터를 Qoo10 업로드 형식으로 변환합니다
	@if [ -z "$(INPUT_FILE)" ]; then \
		echo "사용법: make oliveyoung-upload INPUT_FILE=data/oliveyoung_products_20250807_103114.xlsx"; \
		exit 1; \
	fi
	@echo "🚀 Oliveyoung 데이터 Qoo10 업로드 변환 시작: $(INPUT_FILE)"
	@if [ -f "$(INPUT_FILE)" ]; then \
		uv run uploader/oliveyoung_uploader.py --input="$(INPUT_FILE)"; \
	else \
		echo "❌ 입력 파일이 존재하지 않습니다: $(INPUT_FILE)"; \
	fi

asmama-crawl: ## Asmama 베스트셀러 페이지 크롤링을 실행합니다 (LIST_URL 조절 가능)
	@if [ -z "$(LIST_URL)" ]; then \
		LIST_URL="http://www.asmama.com/shop/bestseller.html?xcode=REVIEW"; \
	fi; \
	echo "Asmama 크롤링 시작: $$LIST_URL"; \
	uv run playground/test_crawler.py --list-url=$$LIST_URL

upload-celeb: ## 셀럽 검증된 데이터를 Qoo10 업로드 형식으로 변환합니다
	@echo "🚀 셀럽 검증된 데이터 Qoo10 업로드 변환 시작..."
	@if [ -f "$(DATA_DIR)/validated_products_celeb.xlsx" ]; then \
		$(PYTHON) $(UPLOADER_DIR)/uploader.py --input $(DATA_DIR)/validated_products_celeb.xlsx --templates $(TEMPLATES_DIR) --output $(OUTPUT_DIR); \
	else \
		echo "❌ 셀럽 검증된 데이터가 없습니다. 먼저 validate-celeb을 실행하세요."; \
	fi

validate-celeb: ## 셀럽 정보 필수로 데이터를 검증합니다
	@echo "크롤링 데이터 검증 중 (셀럽 정보 필수)..."
	@if [ -f "$(DATA_DIR)/asmama_products.xlsx" ]; then \
		$(PYTHON) playground/analyze_data.py --input=$(DATA_DIR)/asmama_products.xlsx --validate --require-celeb-info --validated-output=$(DATA_DIR)/validated_products_celeb.xlsx; \
	else \
		echo "❌ 검증할 데이터가 없습니다. 먼저 크롤링을 실행하세요."; \
	fi
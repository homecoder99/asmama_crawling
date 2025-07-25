.PHONY: help install crawl test test-unit test-integration clean setup analyze validate playground

# Default goal
.DEFAULT_GOAL := help

# Variables
PYTHON := source .venv/bin/activate && python
PIP := source .venv/bin/activate && uv pip
PYTEST := source .venv/bin/activate && pytest
BLACK := source .venv/bin/activate && black
FLAKE8 := source .venv/bin/activate && flake8
MYPY := source .venv/bin/activate && mypy
DATA_DIR := data
LOGS_DIR := logs
TEST_DIR := tests

help: ## 사용 가능한 명령어를 표시합니다
	@echo "Asmama 크롤러 - 사용 가능한 명령어:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "예시:"
	@echo "  make install                    # 의존성 설치"
	@echo "  make crawl                      # 기본 크롤링 실행"
	@echo "  make validate                   # 데이터 검증 및 정리"
	@echo "  make analyze                    # 데이터 분석 보고서 생성"
	@echo "  make workflow                   # 전체 워크플로우 실행"
	@echo "  make playground-test LIST_URL=\"URL\"  # 리스트 페이지 테스트"
	@echo "  make test                       # 전체 테스트 실행"
	@echo "  make clean                      # 로그 및 임시 파일 정리"

install: ## 의존성을 설치합니다
	@echo "의존성 설치 중..."
	uv venv .venv
	$(PIP) install -r requirements.txt
	$(PYTHON) -m playwright install chromium
	@echo "의존성 설치 완료!"

setup: install ## 프로젝트 초기 설정을 수행합니다
	@echo "프로젝트 초기 설정 중..."
	mkdir -p $(DATA_DIR) $(LOGS_DIR) $(TEST_DIR)
	mkdir -p playground/results
	@echo "디렉토리 구조 생성 완료:"
	@echo "  📁 $(DATA_DIR)/ - 크롤링 데이터 저장"
	@echo "  📁 $(LOGS_DIR)/ - 로그 파일 저장"
	@echo "  📁 playground/results/ - 분석 결과 저장"
	@echo "설정 완료!"

crawl: ## 기본 크롤링을 실행합니다 (branduid=1234567)
	@echo "Asmama 크롤링 시작..."
	$(PYTHON) main.py --branduid=1234567 --output=$(DATA_DIR)/asmama_products.xlsx

crawl-list: ## 리스트 페이지에서 크롤링을 실행합니다
	@echo "리스트 페이지 크롤링 시작..."
	$(PYTHON) main.py --list-url="http://www.asmama.com/shop/list.html" --max-items=30 --output=$(DATA_DIR)/asmama_products.xlsx

crawl-custom: ## 사용자 정의 branduid로 크롤링을 실행합니다 (BRANDUID 환경변수 필요)
	@if [ -z "$(BRANDUID)" ]; then \
		echo "사용법: make crawl-custom BRANDUID=1234567"; \
		exit 1; \
	fi
	@echo "사용자 정의 크롤링 시작: branduid=$(BRANDUID)"
	$(PYTHON) main.py --branduid=$(BRANDUID) --output=$(DATA_DIR)/asmama_products.xlsx

test: ## 전체 테스트를 실행합니다
	@echo "전체 테스트 실행 중..."
	$(PYTEST) $(TEST_DIR) -v --tb=short

test-unit: ## 단위 테스트만 실행합니다
	@echo "단위 테스트 실행 중..."
	$(PYTEST) $(TEST_DIR)/test_*.py -v --tb=short -k "not integration"

test-integration: ## 통합 테스트만 실행합니다
	@echo "통합 테스트 실행 중..."
	$(PYTEST) $(TEST_DIR)/test_integration.py -v --tb=short

test-crawler: ## 크롤러 테스트만 실행합니다
	@echo "크롤러 테스트 실행 중..."
	$(PYTEST) $(TEST_DIR)/test_crawler.py -v

lint: ## 코드 품질 검사를 실행합니다
	@echo "코드 품질 검사 중..."
	$(FLAKE8) crawler/ main.py --max-line-length=100
	$(BLACK) --check crawler/ main.py
	$(MYPY) crawler/ main.py

format: ## 코드 포맷팅을 적용합니다
	@echo "코드 포맷팅 적용 중..."
	$(BLACK) crawler/ main.py

clean: ## 로그 및 임시 파일을 정리합니다
	@echo "파일 정리 중..."
	rm -rf $(LOGS_DIR)/*.log
	rm -rf __pycache__/
	rm -rf crawler/__pycache__/
	rm -rf tests/__pycache__/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete
	@echo "정리 완료!"

clean-data: ## 크롤링 데이터 파일을 삭제합니다
	@echo "데이터 파일 삭제 중..."
	rm -rf $(DATA_DIR)/*.xlsx
	rm -rf $(DATA_DIR)/*.json
	@echo "데이터 파일 삭제 완료!"

clean-logs: ## 검증 로그 파일을 삭제합니다
	@echo "검증 로그 파일 삭제 중..."
	rm -rf $(LOGS_DIR)/validation_*.json
	rm -rf $(LOGS_DIR)/validation_*.txt
	@echo "검증 로그 파일 삭제 완료!"

clean-results: ## playground 결과 파일을 삭제합니다
	@echo "playground 결과 파일 삭제 중..."
	rm -rf playground/results/*.txt
	rm -rf playground/results/*.json
	@echo "playground 결과 파일 삭제 완료!"

clean-all: clean clean-data clean-logs clean-results ## 모든 임시 파일을 삭제합니다

logs: ## 최근 로그 파일을 표시합니다
	@echo "최근 로그 파일들:"
	@ls -la $(LOGS_DIR)/*.log 2>/dev/null || echo "로그 파일이 없습니다."

stats: ## 크롤링 통계를 표시합니다
	@echo "크롤링 데이터 통계:"
	@if [ -f "$(DATA_DIR)/asmama_products.xlsx" ]; then \
		$(PYTHON) -c "import pandas as pd; df=pd.read_excel('$(DATA_DIR)/asmama_products.xlsx'); print(f'총 제품 수: {len(df)}'); print(f'컬럼: {list(df.columns)}')"; \
	else \
		echo "크롤링 데이터가 없습니다."; \
	fi

# 데이터 분석 및 검증 관련 명령어
analyze: ## 크롤링 데이터를 분석합니다
	@echo "크롤링 데이터 분석 중..."
	@if [ -f "$(DATA_DIR)/asmama_products.xlsx" ]; then \
		$(PYTHON) playground/analyze_data.py --input=$(DATA_DIR)/asmama_products.xlsx --output=playground/results/analysis_report.txt; \
	else \
		echo "❌ 분석할 데이터가 없습니다. 먼저 크롤링을 실행하세요."; \
	fi

validate: ## 크롤링 데이터를 검증하고 정리합니다
	@echo "크롤링 데이터 검증 중..."
	@if [ -f "$(DATA_DIR)/asmama_products.xlsx" ]; then \
		$(PYTHON) playground/analyze_data.py --input=$(DATA_DIR)/asmama_products.xlsx --validate --validated-output=$(DATA_DIR)/validated_products.xlsx; \
	else \
		echo "❌ 검증할 데이터가 없습니다. 먼저 크롤링을 실행하세요."; \
	fi

validate-celeb: ## 셀럽 정보 필수로 데이터를 검증합니다
	@echo "크롤링 데이터 검증 중 (셀럽 정보 필수)..."
	@if [ -f "$(DATA_DIR)/asmama_products.xlsx" ]; then \
		$(PYTHON) playground/analyze_data.py --input=$(DATA_DIR)/asmama_products.xlsx --validate --require-celeb-info --validated-output=$(DATA_DIR)/validated_products_celeb.xlsx; \
	else \
		echo "❌ 검증할 데이터가 없습니다. 먼저 크롤링을 실행하세요."; \
	fi

analyze-detailed: ## 상세 데이터 분석을 수행합니다
	@echo "상세 데이터 분석 중..."
	@if [ -f "$(DATA_DIR)/asmama_products.xlsx" ]; then \
		$(PYTHON) playground/analyze_data.py --input=$(DATA_DIR)/asmama_products.xlsx --detailed --output=playground/results/detailed_analysis.txt; \
	else \
		echo "❌ 분석할 데이터가 없습니다. 먼저 크롤링을 실행하세요."; \
	fi

# Playground 스크립트 명령어
playground-unit-test: ## 크롤러 단일 제품 테스트를 실행합니다
	@echo "크롤러 단일 제품 테스트 실행 중..."
	@if [ -z "$(BRANDUID)" ]; then \
		echo "사용법: make playground-unit-test BRANDUID=1234567"; \
		exit 1; \
	fi
	$(PYTHON) playground/test_crawler.py --branduid=$(BRANDUID)

playground-test: ## 크롤러 리스트 테스트를 실행합니다
	@echo "크롤러 리스트 테스트 실행 중..."
	@if [ -z "$(LIST_URL)" ]; then \
		echo "사용법: make playground-test LIST_URL=\"http://www.asmama.com/shop/bestseller.html?xcode=REVIEW\""; \
		exit 1; \
	fi
	$(PYTHON) playground/test_crawler.py --list-url="$(LIST_URL)"

dev: ## 개발 환경을 준비합니다 (설치 + 테스트)
	@echo "개발 환경 준비 중..."
	$(MAKE) install
	$(MAKE) test-unit
	@echo "개발 환경 준비 완료!"

demo: ## 데모 크롤링을 실행합니다 (테스트용 branduid 사용)
	@echo "데모 크롤링 실행 중..."
	@echo "주의: 실제 사이트 구조에 맞게 셀렉터 수정이 필요할 수 있습니다."
	$(PYTHON) main.py --branduid=test123 --output=$(DATA_DIR)/demo_products.xlsx

# 워크플로우 명령어
workflow: ## 전체 워크플로우를 실행합니다 (크롤링 → 검증 → 분석)
	@echo "🚀 전체 워크플로우 시작..."
	@echo "1️⃣ 크롤링 실행 중..."
	$(MAKE) crawl-list
	@echo "2️⃣ 데이터 검증 중..."
	$(MAKE) validate
	@echo "3️⃣ 데이터 분석 중..."
	$(MAKE) analyze
	@echo "✅ 전체 워크플로우 완료!"
	@echo ""
	@echo "결과 파일:"
	@echo "  📊 원본 데이터: $(DATA_DIR)/asmama_products.xlsx"
	@echo "  ✅ 검증된 데이터: $(DATA_DIR)/validated_products.xlsx"
	@echo "  📋 분석 보고서: playground/results/analysis_report.txt"
	@echo "  📝 검증 로그: logs/validation_stats.json"

workflow-custom: ## 사용자 정의 branduid로 워크플로우를 실행합니다
	@if [ -z "$(BRANDUID)" ]; then \
		echo "사용법: make workflow-custom BRANDUID=1234567"; \
		exit 1; \
	fi
	@echo "🚀 사용자 정의 워크플로우 시작: branduid=$(BRANDUID)"
	@echo "1️⃣ 크롤링 실행 중..."
	$(MAKE) crawl-custom BRANDUID=$(BRANDUID)
	@echo "2️⃣ 데이터 검증 중..."
	$(MAKE) validate
	@echo "3️⃣ 데이터 분석 중..."
	$(MAKE) analyze
	@echo "✅ 전체 워크플로우 완료!"

quick-test: ## 빠른 테스트 워크플로우 (단일 branduid → 검증 → 분석)
	@echo "⚡ 빠른 테스트 워크플로우 시작..."
	$(MAKE) crawl BRANDUID=1234567
	$(MAKE) validate
	$(MAKE) analyze
	@echo "✅ 빠른 테스트 완료!"

# CI/CD 관련 명령어
ci: install lint test ## CI 파이프라인을 실행합니다

# 도움말
install-help: ## 설치 관련 도움말을 표시합니다
	@echo "설치 관련 도움말:"
	@echo ""
	@echo "1. uv, Python 3.8+ 필요"
	@echo "2. make install 실행"
	@echo "3. make demo 로 테스트"
	@echo ""
	@echo "문제 해결:"
	@echo "- Playwright 설치 실패 시: source .venv/bin/activate && python -m playwright install chromium"
	@echo "- 권한 문제 시: source .venv/bin/activate && uv pip install --user -r requirements.txt"
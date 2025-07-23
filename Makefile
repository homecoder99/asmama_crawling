.PHONY: help install crawl test test-unit test-integration clean setup

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
	@echo "  make install          # 의존성 설치"
	@echo "  make crawl            # 기본 크롤링 실행"
	@echo "  make test             # 전체 테스트 실행"
	@echo "  make clean            # 로그 및 임시 파일 정리"

install: ## 의존성을 설치합니다
	@echo "의존성 설치 중..."
	uv venv .venv
	$(PIP) install -r requirements.txt
	$(PYTHON) -m playwright install chromium
	@echo "의존성 설치 완료!"

setup: install ## 프로젝트 초기 설정을 수행합니다
	@echo "프로젝트 초기 설정 중..."
	mkdir -p $(DATA_DIR) $(LOGS_DIR) $(TEST_DIR)
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

dev: ## 개발 환경을 준비합니다 (설치 + 테스트)
	@echo "개발 환경 준비 중..."
	$(MAKE) install
	$(MAKE) test-unit
	@echo "개발 환경 준비 완료!"

demo: ## 데모 크롤링을 실행합니다 (테스트용 branduid 사용)
	@echo "데모 크롤링 실행 중..."
	@echo "주의: 실제 사이트 구조에 맞게 셀렉터 수정이 필요할 수 있습니다."
	$(PYTHON) main.py --branduid=test123 --output=$(DATA_DIR)/demo_products.xlsx

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
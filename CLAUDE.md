# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Playwright-based web crawler designed to scrape product data from multiple e-commerce websites. Currently supports:

- **Asmama**: `http://www.asmama.com/shop/shopdetail.html?branduid={branduid}`
- **Oliveyoung**: `https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo={goodsNo}`

The crawler outputs data to Excel files with PostgreSQL-compatible schema and includes comprehensive anti-bot measures.

## Essential Commands

### Setup and Installation

```bash
make install          # Install dependencies + Playwright browser (uses uv)
make setup           # Create data/logs directories + upload templates
make dev             # Full dev environment setup (install + unit tests)
```

### Running Crawlers

#### Asmama Crawler

```bash
make crawl                           # Default crawl (branduid=1234567)
make crawl-custom BRANDUID=1234567  # Custom branduid
make crawl-list                      # Crawl from list page
python main.py --site=asmama --branduid=X --output=path.xlsx  # Direct execution
```

#### Oliveyoung Crawler

```bash
# 단일 제품 크롤링
python main.py --site=oliveyoung --goods-no=A000000192405 --output=oliveyoung_products.xlsx

# 특정 카테고리 크롤링 (판매순 정렬, 제한된 개수)
python main.py --site=oliveyoung --category-id=100000100010001 --max-items-per-category=20

# 모든 카테고리 크롤링 (카테고리당 15개씩, 판매순)
python main.py --site=oliveyoung --all-categories --max-items-per-category=15

# 기존 URL 방식 (호환성)
python main.py --site=oliveyoung --list-url="https://www.oliveyoung.co.kr/store/display/getMCategoryList.do?dispCatNo=100000100010001" --max-items=50

# PostgreSQL에도 저장 (듀얼 스토리지)
python main.py --site=oliveyoung --all-categories --save-to-db
```

#### Multi-site Support

```bash
python main.py --site=asmama --branduid=1234567    # Asmama single product
python main.py --site=oliveyoung --goods-no=A123   # Oliveyoung single product
```

### Testing

```bash
make test            # All tests
make test-unit       # Unit tests only (excludes integration)
make test-integration # Integration tests only
pytest tests/test_specific.py -v    # Single test file
```

### Code Quality

```bash
make lint            # flake8 + black check + mypy
make format          # Apply black formatting
make ci             # Full CI pipeline (install + lint + test)
```

### Data Processing & Upload

```bash
make validate        # Validate and clean crawled data
make validate-celeb  # Validate data requiring celebrity info
make analyze         # Generate analysis report
make upload          # Convert to Qoo10 upload format
make workflow        # Full workflow: crawl → validate → analyze → upload
```

### Development Tools

#### Asmama Development Tools

```bash
python playground/test_crawler.py --branduid=1234567
python playground/test_selectors.py --branduid=1234567
python playground/debug_session.py --branduid=1234567 --verbose
python playground/analyze_data.py --input=data/asmama_products.xlsx
```

#### Oliveyoung Development Tools

```bash
python playground/test_oliveyoung_crawler.py --goods-no=A000000192405
python playground/test_oliveyoung_selectors.py --goods-no=A000000192405 --verbose
python playground/debug_oliveyoung_session.py --goods-no=A000000192405 --verbose
python playground/debug_oliveyoung_session.py --multi-test A123 A456 A789

# 개선된 크롤러 테스트
python test_improved_oliveyoung.py
```

### Monitoring and Cleanup

```bash
make stats           # Crawling statistics
make logs           # View recent logs
make clean          # Remove logs/cache
make clean-data     # Remove crawling results
```

## Architecture Overview

### Core Crawler Hierarchy

```
BaseCrawler (crawler/base.py)
    ↓ [Abstract base class with Playwright integration]
├── AsmamaCrawler (crawler/asmama.py)
│   ↓ [Asmama-specific implementation]
└── OliveyoungCrawler (crawler/oliveyoung.py)
    ↓ [Oliveyoung-specific implementation]
```

**Key Design Patterns:**

- **Abstract Base Class**: `BaseCrawler` provides common Playwright operations, async context management, and retry logic
- **Dependency Injection**: Storage backends injected into crawlers
- **Async Context Managers**: Proper resource cleanup for browser sessions
- **Semaphore-based Concurrency**: Max 3 concurrent sessions for anti-bot compliance

### Storage Layer

```
BaseStorage (crawler/storage.py)
    ↓ [Abstract storage interface]
├── ExcelStorage      # Primary: Excel files with JSON serialization for arrays
├── JSONStorage       # Development: Direct JSON output
└── PostgresStorage   # PostgreSQL database storage (crawler/db_storage.py)
```

**Important Notes:**

- Excel storage converts Python lists to JSON strings for compatibility
- PostgresStorage converts crawler schema to DB schema automatically
- **Dual Storage Support**: Crawlers can save to both Excel and PostgreSQL simultaneously
- All storage operations are synchronous but called from async context

**Dual Storage Usage:**

```python
from crawler.oliveyoung import OliveyoungCrawler
from crawler.storage import ExcelStorage
from crawler.db_storage import PostgresStorage

excel_storage = ExcelStorage("data/products.xlsx")
db_storage = PostgresStorage()  # Uses DATABASE_URL env var

async with OliveyoungCrawler(storage=excel_storage, db_storage=db_storage) as crawler:
    products = await crawler.crawl_all_categories()
    # Saves to both Excel and PostgreSQL automatically
```

### Data Schema (Current)

```python
{
    "branduid": str,      # Product unique identifier
    "name": str,          # Product name
    "price": int,         # Price in KRW
    "options": List[str], # Product options array
    "image_urls": List[str], # Image URLs array
    "detail_html": str    # Full product page HTML
}
```

### Anti-Bot Strategy

- **Random User-Agents**: 5 realistic browser strings
- **Random Viewports**: 5 common screen resolutions
- **Random Delays**: 1-3 second delays (Asmama), 2-4 seconds (Oliveyoung)
- **Session Limits**: Max 3 concurrent browser contexts (Asmama), Max 1 (Oliveyoung)
- **Cookie Persistence**: Browser context reuse for session continuity
- **Site-specific Rate Limiting**: Conservative batch sizes per site
- **Category-based Throttling**: 5-second delays between categories (Oliveyoung)

## File Organization

```
crawler/           # Core crawling logic
├── base.py       # Abstract base class with Playwright utilities
├── asmama.py     # Asmama-specific crawler implementation
├── oliveyoung.py # Oliveyoung-specific crawler implementation
├── storage.py    # Storage interfaces (Excel/JSON)
├── db_storage.py # PostgreSQL storage implementation
├── utils.py      # Utilities (logging, delays, parsing)
├── cookies.py    # Cookie management system
├── validator.py  # Data validation utilities
├── oliveyoung_*.py # Oliveyoung specialized modules (extractors, categories, etc.)

playground/       # Development and debugging tools
├── test_crawler.py            # Basic Asmama crawler testing
├── test_selectors.py          # Asmama CSS selector validation
├── test_oliveyoung_crawler.py # Basic Oliveyoung crawler testing
├── test_oliveyoung_selectors.py # Oliveyoung CSS selector validation
├── analyze_data.py            # Data analysis and statistics
├── debug_session.py           # Asmama step-by-step debugging
└── debug_oliveyoung_session.py # Oliveyoung step-by-step debugging

uploader/         # Qoo10 upload data transformation
├── uploader.py      # Main upload transformer
├── data_loader.py   # Excel data loading utilities
├── data_adapter.py  # Data source adapter (Excel/PostgreSQL)
├── image_processor.py # Image processing and filtering
├── product_filter.py  # Product filtering logic
└── field_transformer.py # Field mapping and transformation

tests/           # Test suite
├── test_utils.py          # Utility function tests
├── test_storage.py        # Storage layer tests
├── test_integration.py    # End-to-end workflow tests
└── test_oliveyoung_crawler.py # Oliveyoung crawler unit tests

data/           # Crawling output (auto-created)
logs/           # Timestamped log files (auto-created)
main.py         # CLI entry point
config.py       # Configuration constants
```

## New Oliveyoung Features (Category-First Crawling)

### Category-First Architecture

The improved Oliveyoung crawler now follows a category-first approach based on the JavaScript implementation:

1. **Category Extraction**: Automatically extracts categories from the main menu navigation
2. **Sales Ranking**: Uses `prdSort=02` parameter for sales-based sorting
3. **Limited Crawling**: Configurable item limits per category (default: 15 items)
4. **Batch Processing**: Processes categories sequentially with throttling

### New Crawling Methods

- `crawl_all_categories()`: Crawls all available categories with per-category limits
- `crawl_from_category()`: Crawls a specific category by ID with sales ranking
- `_extract_categories()`: Extracts category IDs from the main navigation menu
- `_extract_goods_no_list_from_category()`: Gets product IDs from category pages

### Usage Examples

```bash
# Crawl all categories (15 items each, sales-ranked)
python main.py --site=oliveyoung --all-categories --max-items-per-category=15

# Crawl specific category with more items
python main.py --site=oliveyoung --category-id=100000100010001 --max-items-per-category=25

# Test the improved crawler
python test_improved_oliveyoung.py
```

## Development Workflow

### Adding New Selectors (Asmama)

1. Use `playground/test_selectors.py --branduid=X` to test CSS selectors
2. Update selectors in `crawler/asmama.py` within `_extract_product_data()`
3. Add FIX ME comments when selectors need site-specific tuning
4. Test with `playground/debug_session.py` for visual debugging

### Adding New Selectors (Oliveyoung)

1. Use `playground/test_oliveyoung_selectors.py --goods-no=X --verbose` to test CSS selectors
2. Update selectors in `crawler/oliveyoung.py` within `_extract_product_data()`
3. Add FIX ME comments when selectors need site-specific tuning
4. Test with `playground/debug_oliveyoung_session.py` for visual debugging

### Adding New Sites

1. Create new crawler class inheriting from `BaseCrawler` in `crawler/{site}.py`
2. Implement required abstract methods: `crawl_single_product()` and `crawl_from_branduid_list()`
3. Add site-specific data extraction in `_extract_product_data()`
4. Update `main.py` to support new site option
5. Create playground scripts for testing and debugging
6. Add unit tests following the pattern in `tests/test_oliveyoung_crawler.py`

### Schema Changes

1. Update data structure in both `crawler/asmama.py` and `crawler/oliveyoung.py`
2. Add FIX ME comments in `crawler/storage.py` for PostgreSQL compatibility
3. Update column ordering in `ExcelStorage.save()` method
4. Update documentation in this file's data schema section
5. Ensure both crawlers maintain schema compatibility for unified data processing

### Testing Strategy

- **Unit Tests**: Mock Playwright responses, test data parsing logic (both sites)
- **Integration Tests**: Use real browser automation but avoid actual site hits
- **Playground Scripts**: Manual testing against real website (use responsibly for both Asmama and Oliveyoung)
- **Site-specific Testing**: Use appropriate playground scripts for each site

## Configuration

### Environment Variables

```bash
LOG_LEVEL=DEBUG|INFO|WARNING|ERROR    # Logging verbosity
DATABASE_URL=postgresql://...          # Future PostgreSQL connection
MAX_WORKERS=1                         # Override concurrent sessions
REQUEST_TIMEOUT=60                    # Override request timeout
```

### Config File (`config.py`)

Key settings that may need adjustment:

- `USER_AGENT`: Default browser string
- `REQUEST_TIMEOUT`: HTTP request timeout (30s)
- `MAX_RETRIES`: Retry attempts for failed requests (3)
- `RETRY_DELAY`: Delay between retries (5s)

## Logging System

**Log Locations**: `logs/crawl_{timestamp}.log`

**Success Format**: Standard Python logging

```
2024-01-01 12:00:00 - AsmamaCrawler - INFO - 제품 크롤링 성공: 1234567
2024-01-01 12:00:00 - OliveyoungCrawler - INFO - Oliveyoung 제품 크롤링 성공: A000000192405 - 제품명
```

**Error Format**: JSON lines for structured parsing

```json
{"branduid": "1234567", "reason": "페이지 로드 실패", "trace": "...", "timestamp": "2024-01-01T12:00:00"}
{"goods_no": "A000000192405", "reason": "Oliveyoung 페이지 로드 실패", "trace": "...", "timestamp": "2024-01-01T12:00:00"}
```

## Common Issues

### Playwright Browser Installation

```bash
python -m playwright install chromium  # Reinstall browser
make install                          # Full setup including browser
```

### CSS Selector Failures

#### Asmama Selectors

Selectors in `crawler/asmama.py` marked with FIX ME comments need site-specific updates:

1. Run `playground/test_selectors.py` to identify working selectors
2. Update `_extract_product_data()` method with new selectors
3. Test with `playground/debug_session.py --headless=false` for visual confirmation

#### Oliveyoung Selectors

Selectors in `crawler/oliveyoung.py` may need updates for site changes:

1. Run `playground/test_oliveyoung_selectors.py --goods-no=X --verbose` to identify working selectors
2. Update `_extract_product_data()` method with new selectors
3. Test with `playground/debug_oliveyoung_session.py --goods-no=X` for visual confirmation

### Memory/Performance Issues

- Reduce `max_workers` in crawler initialization (default: 3 for Asmama, 1 for Oliveyoung)
- Use `make clean` to remove accumulated cache files
- Monitor with `make stats` for data volume
- Consider site-specific batch sizes: Asmama (15), Oliveyoung (10)

## Korean Language Requirements

All functions and classes must include Korean docstrings. When adding new code:

```python
def new_function(param: str) -> bool:
    """
    새로운 함수의 목적을 한국어로 설명한다.

    Args:
        param: 매개변수 설명

    Returns:
        반환값 설명
    """
```

## Package Management

This project uses **uv** for Python package management instead of pip. All Makefile commands are configured to use uv automatically:

```bash
# Virtual environment is managed via uv
make install    # Creates .venv and installs dependencies with uv
source .venv/bin/activate    # Activate virtual environment manually if needed
```

## Data Processing Pipeline

### Validation System

The project includes a comprehensive data validation system in `crawler/validator.py`:

- **Product filtering**: Removes invalid/incomplete products
- **Celebrity information**: Optional requirement for specific validation modes
- **Data cleaning**: Standardizes formats and removes duplicates

### Upload Transformation

The `uploader/` module converts crawled data to Qoo10-compatible format:

- **Template-based**: Uses Excel templates for consistent formatting
- **Image processing**: Advanced filtering and validation of product images
- **Brand filtering**: Excludes banned brands and applies warning keyword filters
- **Field mapping**: Transforms crawler data to marketplace-specific fields
- **Data Adapter Pattern**: Supports both Excel and PostgreSQL as data sources

#### Using PostgreSQL as Data Source

```bash
# Upload from PostgreSQL instead of Excel
cd uploader
python -c "
from oliveyoung_uploader import OliveyoungUploader
uploader = OliveyoungUploader(templates_dir='templates')
uploader.load_templates()
uploader.process_crawled_data(source_type='postgres', source_filter='oliveyoung')
"
```

## Task Master AI Integration

This project uses Task Master AI for progress tracking. Current completion: 75% (9/12 tasks).
Use `make test` to verify acceptance criteria: 30+ items crawled, comprehensive logging, all tests passing.

## Task Master AI Instructions

**Import Task Master's development workflow commands and guidelines, treat as if import is in the main CLAUDE.md file.**
@./.taskmaster/CLAUDE.md

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.

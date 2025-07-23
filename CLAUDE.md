# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Playwright-based web crawler specifically designed to scrape product data from Asmama website (`http://www.asmama.com/shop/shopdetail.html?branduid={branduid}`). The crawler outputs data to Excel files with PostgreSQL-compatible schema and includes comprehensive anti-bot measures.

## Essential Commands

### Setup and Installation
```bash
make install          # Install dependencies + Playwright browser
make setup           # Create data/logs directories
make dev             # Full dev environment setup (install + unit tests)
```

### Running Crawlers
```bash
make crawl                           # Default crawl (branduid=1234567)
make crawl-custom BRANDUID=1234567  # Custom branduid
make crawl-list                      # Crawl from list page
python main.py --branduid=X --output=path.xlsx  # Direct execution
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

### Development Tools
```bash
# Playground scripts for experimentation
python playground/test_crawler.py --branduid=1234567
python playground/test_selectors.py --branduid=1234567  
python playground/debug_session.py --branduid=1234567 --verbose
python playground/analyze_data.py --input=data/asmama_products.xlsx
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
AsmamaCrawler (crawler/asmama.py)
    ↓ [Asmama-specific implementation]
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
├── ExcelStorage    # Primary: Excel files with JSON serialization for arrays
└── JSONStorage     # Development: Direct JSON output
```

**Important Notes:**
- Excel storage converts Python lists to JSON strings for compatibility
- Schema includes FIX ME comments for future PostgreSQL migration
- All storage operations are synchronous but called from async context

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
- **Random Delays**: 1-3 second delays between requests
- **Session Limits**: Max 3 concurrent browser contexts
- **Cookie Persistence**: Browser context reuse for session continuity

## File Organization

```
crawler/           # Core crawling logic
├── base.py       # Abstract base class with Playwright utilities
├── asmama.py     # Asmama-specific crawler implementation  
├── storage.py    # Storage interfaces (Excel/JSON)
└── utils.py      # Utilities (logging, delays, parsing)

playground/       # Development and debugging tools
├── test_crawler.py    # Basic crawler testing
├── test_selectors.py  # CSS selector validation
├── analyze_data.py    # Data analysis and statistics
└── debug_session.py   # Step-by-step debugging

tests/           # Test suite
├── test_utils.py       # Utility function tests
├── test_storage.py     # Storage layer tests  
└── test_integration.py # End-to-end workflow tests

data/           # Crawling output (auto-created)
logs/           # Timestamped log files (auto-created)
main.py         # CLI entry point
config.py       # Configuration constants
```

## Development Workflow

### Adding New Selectors
1. Use `playground/test_selectors.py --branduid=X` to test CSS selectors
2. Update selectors in `crawler/asmama.py` within `_extract_product_data()`
3. Add FIX ME comments when selectors need site-specific tuning
4. Test with `playground/debug_session.py` for visual debugging

### Schema Changes
1. Update data structure in `crawler/asmama.py`
2. Add FIX ME comments in `crawler/storage.py` for PostgreSQL compatibility
3. Update column ordering in `ExcelStorage.save()` method
4. Update documentation in README.md data schema table

### Testing Strategy
- **Unit Tests**: Mock Playwright responses, test data parsing logic
- **Integration Tests**: Use real browser automation but avoid actual site hits
- **Playground Scripts**: Manual testing against real website (use responsibly)

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
```

**Error Format**: JSON lines for structured parsing
```json
{"branduid": "1234567", "reason": "페이지 로드 실패", "trace": "...", "timestamp": "2024-01-01T12:00:00"}
```

## Common Issues

### Playwright Browser Installation
```bash
python -m playwright install chromium  # Reinstall browser
make install                          # Full setup including browser
```

### CSS Selector Failures
Selectors in `crawler/asmama.py` marked with FIX ME comments need site-specific updates:
1. Run `playground/test_selectors.py` to identify working selectors
2. Update `_extract_product_data()` method with new selectors
3. Test with `playground/debug_session.py --headless=false` for visual confirmation

### Memory/Performance Issues
- Reduce `max_workers` in crawler initialization (default: 3)
- Use `make clean` to remove accumulated cache files
- Monitor with `make stats` for data volume

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

## Task Master AI Integration

This project uses Task Master AI for progress tracking. Current completion: 75% (9/12 tasks).
Use `make test` to verify acceptance criteria: 30+ items crawled, comprehensive logging, all tests passing.
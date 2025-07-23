"""통합 테스트."""

import pytest
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from crawler.asmama import AsmamaCrawler
from crawler.storage import JSONStorage


class TestIntegration:
    """전체 크롤링 프로세스 통합 테스트."""
    
    @pytest.mark.asyncio
    async def test_crawler_with_mock_browser(self):
        """모킹된 브라우저로 크롤러 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 저장소 설정
            storage_path = Path(temp_dir) / "test.json"
            storage = JSONStorage(str(storage_path))
            
            # 크롤러 초기화
            crawler = AsmamaCrawler(storage=storage, max_workers=1)
            
            # 브라우저 모킹
            mock_page = AsyncMock()
            mock_page.goto = AsyncMock(return_value=True)
            mock_page.query_selector = AsyncMock()
            mock_page.query_selector_all = AsyncMock(return_value=[])
            mock_page.content = AsyncMock(return_value="<html>Test HTML</html>")
            
            # 제품 데이터 모킹
            mock_element = AsyncMock()
            mock_element.inner_text = AsyncMock(return_value="Test Product")
            mock_element.get_attribute = AsyncMock(return_value="test.jpg")
            mock_element.inner_html = AsyncMock(return_value="<div>Product details</div>")
            
            mock_page.query_selector.return_value = mock_element
            
            mock_context = AsyncMock()
            mock_context.new_page = AsyncMock(return_value=mock_page)
            mock_context.close = AsyncMock()
            
            mock_browser = AsyncMock()
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_browser.close = AsyncMock()
            
            mock_playwright = AsyncMock()
            mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_playwright.stop = AsyncMock()
            
            with patch('crawler.base.async_playwright') as mock_async_playwright:
                mock_async_playwright.return_value.start = AsyncMock(return_value=mock_playwright)
                
                # 크롤러 실행
                async with crawler:
                    result = await crawler.crawl_single_product("test123")
                
                # 결과 검증
                assert result is not None
                assert result["branduid"] == "test123"
                assert result["name"] == "Test Product"
                
                # 저장 검증
                saved_data = storage.load()
                assert len(saved_data) == 1
                assert saved_data[0]["branduid"] == "test123"
    
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """에러 처리 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir) / "test.json"
            storage = JSONStorage(str(storage_path))
            
            crawler = AsmamaCrawler(storage=storage, max_workers=1)
            
            # 브라우저 시작 실패 모킹
            with patch('crawler.base.async_playwright') as mock_async_playwright:
                mock_async_playwright.return_value.start.side_effect = Exception("Browser failed")
                
                # 크롤러 시작 시 에러 발생해야 함
                with pytest.raises(Exception, match="Browser failed"):
                    async with crawler:
                        pass
    
    def test_sync_crawl_interface(self):
        """동기 인터페이스 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir) / "test.json"
            storage = JSONStorage(str(storage_path))
            
            crawler = AsmamaCrawler(storage=storage, max_workers=1)
            
            # 비동기 메서드 모킹
            async def mock_crawl_single(branduid):
                return {
                    "branduid": branduid,
                    "name": f"Product {branduid}",
                    "price": 10000
                }
            
            with patch.object(crawler, 'crawl_single_product', side_effect=mock_crawl_single):
                with patch.object(crawler, '__aenter__', return_value=crawler):
                    with patch.object(crawler, '__aexit__', return_value=None):
                        # 동기 메서드 실행
                        results = crawler.crawl(["test1", "test2"])
                        
                        # 결과 검증
                        assert len(results) == 2
                        assert all(isinstance(r, dict) for r in results)
    
    @pytest.mark.asyncio
    async def test_concurrent_crawling(self):
        """동시 크롤링 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir) / "test.json"
            storage = JSONStorage(str(storage_path))
            
            crawler = AsmamaCrawler(storage=storage, max_workers=2)
            
            # 다중 제품 크롤링 모킹
            async def mock_crawl_single(branduid):
                await asyncio.sleep(0.1)  # 시뮬레이션 지연
                return {
                    "branduid": branduid,
                    "name": f"Product {branduid}",
                    "price": 10000
                }
            
            with patch.object(crawler, '__aenter__', return_value=crawler):
                with patch.object(crawler, '__aexit__', return_value=None):
                    with patch.object(crawler, 'crawl_single_product', side_effect=mock_crawl_single):
                        
                        # 다중 제품 동기 크롤링
                        branduid_list = ["test1", "test2", "test3"]
                        results = crawler.crawl(branduid_list)
                        
                        # 결과 검증
                        assert len(results) == 3
                        assert all(r["branduid"] in branduid_list for r in results)
    
    def test_storage_integration(self):
        """저장소 통합 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir) / "integration_test.json"
            storage = JSONStorage(str(storage_path))
            
            # 테스트 데이터
            test_products = [
                {
                    "branduid": "int_test_1",
                    "name": "Integration Test Product 1",
                    "price": 15000,
                    "options": ["red", "blue"],
                    "image_urls": ["http://example.com/image1.jpg"],
                    "detail_html": "<div>Details 1</div>"
                },
                {
                    "branduid": "int_test_2",
                    "name": "Integration Test Product 2",
                    "price": 25000,
                    "options": ["small", "large"],
                    "image_urls": ["http://example.com/image2.jpg"],
                    "detail_html": "<div>Details 2</div>"
                }
            ]
            
            # 저장 테스트
            for product in test_products:
                result = storage.save(product)
                assert result is True
            
            # 로드 및 검증
            loaded_data = storage.load()
            assert len(loaded_data) == 2
            
            # 데이터 검증
            loaded_branduid_list = [item["branduid"] for item in loaded_data]
            assert "int_test_1" in loaded_branduid_list
            assert "int_test_2" in loaded_branduid_list
            
            # 파일 존재 검증
            assert storage_path.exists()
            assert storage_path.stat().st_size > 0
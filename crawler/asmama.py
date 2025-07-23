"""Asmama 웹사이트 전용 크롤러 구현."""

import asyncio
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
import traceback

from .base import BaseCrawler
from .utils import log_error, parse_price, clean_text, extract_options_from_text


class AsmamaCrawler(BaseCrawler):
    """
    Asmama 웹사이트 전용 크롤러.
    
    http://www.asmama.com/shop/shopdetail.html?branduid={branduid} 형식의
    URL에서 제품 정보를 크롤링한다.
    """
    
    BASE_URL = "http://www.asmama.com"
    PRODUCT_URL_TEMPLATE = "http://www.asmama.com/shop/shopdetail.html?branduid={branduid}"
    
    def __init__(self, storage: Any = None, max_workers: int = 3):
        """
        Asmama 크롤러를 초기화한다.
        
        Args:
            storage: 데이터 저장소 인스턴스
            max_workers: 최대 동시 세션 수 (안티봇 대응)
        """
        super().__init__(storage, max_workers)
        self.semaphore = asyncio.Semaphore(max_workers)  # 동시성 제어
        
    async def crawl_single_product(self, branduid: str) -> Optional[Dict[str, Any]]:
        """
        단일 제품을 크롤링한다.
        
        Args:
            branduid: 제품의 branduid
            
        Returns:
            크롤링된 제품 데이터 또는 None (실패 시)
        """
        async with self.semaphore:
            url = self.PRODUCT_URL_TEMPLATE.format(branduid=branduid)
            
            try:
                context = await self.create_context()
                page = await self.create_page(context)
                
                # 페이지 로드
                if not await self.safe_goto(page, url):
                    log_error(self.logger, branduid, "페이지 로드 실패", None)
                    return None
                
                # 제품 데이터 추출
                product_data = await self._extract_product_data(page, branduid)
                
                await context.close()
                
                if product_data:
                    self.logger.info(f"제품 크롤링 성공: {branduid}")
                    # 데이터 저장
                    if self.storage:
                        self.storage.save(product_data)
                else:
                    log_error(self.logger, branduid, "제품 데이터 추출 실패", None)
                
                return product_data
                
            except Exception as e:
                error_trace = traceback.format_exc()
                log_error(self.logger, branduid, str(e), error_trace)
                return None
    
    async def crawl_from_list(
        self, 
        list_url: str, 
        max_items: int = 30
    ) -> List[Dict[str, Any]]:
        """
        리스트 페이지에서 여러 제품을 크롤링한다.
        
        Args:
            list_url: 제품 리스트 페이지 URL
            max_items: 최대 크롤링 아이템 수
            
        Returns:
            크롤링된 제품 데이터 목록
        """
        try:
            # 리스트 페이지에서 branduid 목록 추출
            branduid_list = await self._extract_branduid_list(list_url, max_items)
            
            if not branduid_list:
                self.logger.warning("리스트 페이지에서 제품 목록을 찾을 수 없음")
                return []
            
            self.logger.info(f"리스트에서 {len(branduid_list)}개 제품 발견")
            
            # 각 제품 크롤링 (동시성 제어 적용)
            tasks = [self.crawl_single_product(branduid) for branduid in branduid_list]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 성공한 결과만 필터링
            products = [
                result for result in results 
                if isinstance(result, dict) and result is not None
            ]
            
            self.logger.info(f"리스트 크롤링 완료: {len(products)}/{len(branduid_list)}")
            return products
            
        except Exception as e:
            self.logger.error(f"리스트 크롤링 실패: {str(e)}", exc_info=True)
            return []
    
    async def _extract_branduid_list(self, list_url: str, max_items: int) -> List[str]:
        """
        리스트 페이지에서 branduid 목록을 추출한다.
        
        Args:
            list_url: 리스트 페이지 URL
            max_items: 최대 아이템 수
            
        Returns:
            branduid 목록
        """
        try:
            context = await self.create_context()
            page = await self.create_page(context)
            
            if not await self.safe_goto(page, list_url):
                return []
            
            # TODO: 실제 사이트 구조에 맞게 셀렉터 수정 필요
            # FIX ME: 실제 Asmama 리스트 페이지 구조 분석 후 셀렉터 업데이트
            product_links = await page.query_selector_all('a[href*="branduid="]')
            
            branduid_list = []
            for link in product_links[:max_items]:
                href = await link.get_attribute('href')
                if href and 'branduid=' in href:
                    # branduid 파라미터 추출
                    branduid = href.split('branduid=')[1].split('&')[0]
                    if branduid not in branduid_list:
                        branduid_list.append(branduid)
            
            await context.close()
            return branduid_list
            
        except Exception as e:
            self.logger.error(f"branduid 목록 추출 실패: {str(e)}")
            return []
    
    async def _extract_product_data(self, page, branduid: str) -> Optional[Dict[str, Any]]:
        """
        제품 페이지에서 데이터를 추출한다.
        
        Args:
            page: Playwright 페이지 인스턴스
            branduid: 제품 branduid
            
        Returns:
            추출된 제품 데이터 또는 None
        """
        try:
            # 페이지 로딩 대기
            await asyncio.sleep(2)  # 안티봇 대응 지연
            
            # FIX ME: 실제 Asmama 사이트 구조에 맞게 셀렉터 수정 필요
            # 현재는 일반적인 쇼핑몰 구조를 가정한 셀렉터 사용
            
            # 제품명 추출
            name = await self.safe_get_text(page, 'h1, .product-title, .item-name, .product-name')
            if not name:
                name = await self.safe_get_text(page, 'title')
            
            # 가격 추출
            price_text = await self.safe_get_text(page, '.price, .product-price, .item-price, .cost')
            price = parse_price(price_text) if price_text else None
            
            # 옵션 추출
            options_text = await self.safe_get_text(page, '.options, .product-options, .item-options')
            options = extract_options_from_text(options_text) if options_text else []
            
            # 이미지 URL 추출
            image_urls = []
            image_elements = await page.query_selector_all('img')
            for img in image_elements:
                src = await img.get_attribute('src')
                if src and ('.jpg' in src or '.png' in src or '.jpeg' in src or '.gif' in src):
                    # 상대 URL을 절대 URL로 변환
                    if src.startswith('/'):
                        src = urljoin(self.BASE_URL, src)
                    elif not src.startswith('http'):
                        src = urljoin(self.BASE_URL, '/' + src)
                    image_urls.append(src)
            
            # 중복 제거
            image_urls = list(dict.fromkeys(image_urls))
            
            # 상세 HTML 추출
            detail_html = ""
            detail_element = await page.query_selector('.product-detail, .item-detail, .description')
            if detail_element:
                detail_html = await detail_element.inner_html()
            else:
                # 전체 페이지 HTML을 백업으로 사용
                detail_html = await page.content()
            
            # FIX ME: 스키마 변경 시 아래 필드 구조 업데이트 필요
            # 현재 스키마: branduid, name, price, options, image_urls, detail_html
            product_data = {
                "branduid": branduid,
                "name": clean_text(name) if name else "",
                "price": price,
                "options": options,
                "image_urls": image_urls,
                "detail_html": detail_html
            }
            
            # 필수 데이터 검증
            if not product_data["name"] and not product_data["detail_html"]:
                return None
            
            return product_data
            
        except Exception as e:
            self.logger.error(f"제품 데이터 추출 실패 ({branduid}): {str(e)}")
            return None
    
    def crawl(self, branduid_list: List[str]) -> List[Dict[str, Any]]:
        """
        동기 방식으로 여러 제품을 크롤링한다.
        
        Args:
            branduid_list: 크롤링할 branduid 목록
            
        Returns:
            크롤링된 제품 데이터 목록
        """
        async def _async_crawl():
            async with self:
                tasks = [self.crawl_single_product(branduid) for branduid in branduid_list]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                products = [
                    result for result in results 
                    if isinstance(result, dict) and result is not None
                ]
                
                return products
        
        return asyncio.run(_async_crawl())
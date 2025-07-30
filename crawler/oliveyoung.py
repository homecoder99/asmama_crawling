"""Oliveyoung 웹사이트 전용 크롤러 구현."""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
import traceback
import re

from .cookies import OliveyoungCookieManager
from playwright.async_api import BrowserContext
from .base import BaseCrawler
from .utils import log_error
from .oliveyoung_extractors import (
    OliveyoungProductExtractor,
    OliveyoungPriceExtractor,
    OliveyoungBenefitExtractor,
    OliveyoungImageExtractor
)
from .oliveyoung_dynamic_content import OliveyoungDynamicContentExtractor


class OliveyoungCrawler(BaseCrawler):
    """
    Oliveyoung 웹사이트 전용 크롤러.
    
    https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo={goodsNo} 형식의
    URL에서 제품 정보를 크롤링한다.
    """
    
    BASE_URL = "https://www.oliveyoung.co.kr"
    PRODUCT_URL_TEMPLATE = "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo={goodsNo}"
    CATEGORY_URL_TEMPLATE = "https://www.oliveyoung.co.kr/store/display/getMCategoryList.do?dispCatNo={categoryId}&prdSort=02&rowsPerPage=48"
    MAIN_PAGE_URL = "https://www.oliveyoung.co.kr/store/main/main.do"
    
    def __init__(self, storage: Any = None, max_workers: int = 1, cookie_file: str = "oy_state.json"):
        """
        Oliveyoung 크롤러를 초기화한다.
        
        Args:
            storage: 데이터 저장소 인스턴스
            max_workers: 최대 동시 세션 수 (서버 부담 경감을 위해 기본값 1)
            cookie_file: 쿠키 저장 파일 경로
        """
        super().__init__(storage, max_workers)
        self.semaphore = asyncio.Semaphore(max_workers)  # 동시성 제어
        
        # 데이터 추출기 초기화
        self.product_extractor = OliveyoungProductExtractor(self.logger)
        self.price_extractor = OliveyoungPriceExtractor(self.logger)
        self.benefit_extractor = OliveyoungBenefitExtractor(self.logger)
        self.image_extractor = OliveyoungImageExtractor(self.logger)
        self.dynamic_extractor = OliveyoungDynamicContentExtractor(self.logger)
        
        # 지속적인 컨텍스트 및 페이지 관리
        self.persistent_context = None
        self.list_page = None  # 상품 목록 페이지를 계속 열어둘 페이지

        # 쿠키 관리
        self.cookie_file = cookie_file
        self.cookie_manager = None
        self.crawl_context = None
        self.page = None
    
    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입."""
        await self.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료."""
        await self.stop()

    async def start(self) -> None:
        """
        크롤러를 시작하고 쿠키 관리자 및 지속적인 브라우저 컨텍스트를 생성한다.
        """
        await super().start()
        
        # 쿠키 관리자 시작
        self.cookie_manager = OliveyoungCookieManager(self.cookie_file)
        await self.cookie_manager.start()
        
        # 쿠키 파일이 없거나 유효하지 않으면 부트스트랩
        if not Path(self.cookie_file).exists():
            self.logger.info("쿠키 파일이 없습니다. 부트스트랩을 실행합니다.")
            await self.cookie_manager.bootstrap_cookies()
        
        # 크롤링용 컨텍스트 생성 (쿠키 관리자를 통해)
        self.crawl_context = await self.cookie_manager.get_crawl_context()
        if not self.crawl_context:
            raise RuntimeError("크롤링용 컨텍스트 생성 실패")
        
        # 기존 persistent_context도 유지 (카테고리 크롤링용)
        self.persistent_context = await self.create_context()
        
        self.logger.info("Oliveyoung 향상된 크롤러 시작 완료")
    
    async def stop(self) -> None:
        """
        크롤러를 종료하고 지속적인 컨텍스트를 정리한다.
        """
        try:
            # 지속적인 페이지와 컨텍스트 정리
            if self.list_page:
                await self.list_page.close()
                self.list_page = None
                self.logger.info("Oliveyoung 상품 목록 페이지 닫기 완료")
                
            if self.persistent_context:
                await self.persistent_context.close()
                self.persistent_context = None
                self.logger.info("Oliveyoung 지속적인 브라우저 컨텍스트 닫기 완료")

            if self.crawl_context:
                await self.crawl_context.close()
                self.crawl_context = None
                self.logger.info("Oliveyoung 크롤링용 브라우저 컨텍스트 닫기 완료")

            if self.cookie_manager:
                await self.cookie_manager.stop()
                self.cookie_manager = None
                self.logger.info("Oliveyoung 쿠키 매니저 종료 완료")

            if self.page:
                await self.page.close()
                self.page = None
                self.logger.info("Oliveyoung 크롤링용 페이지 닫기 완료")

        except Exception as e:
            self.logger.error(f"Oliveyoung 지속적인 리소스 정리 중 오류: {str(e)}")
        
        await super().stop()

    async def get_crawl_context(self) -> Optional[BrowserContext]:
        """
        크롤링용 컨텍스트를 생성한다 (저장된 쿠키 로드).
        
        Returns:
            크롤링용 브라우저 컨텍스트 또는 None
        """
        if not self.cookie_file.exists():
            self.logger.error(f"쿠키 파일이 존재하지 않습니다: {self.cookie_file}")
            return None
            
        try:
            self.logger.info(f"저장된 쿠키 상태 로드: {self.cookie_file}")
            
            context = await self.browser.new_context(
                storage_state=str(self.cookie_file),
                user_agent=self.FIXED_USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
                extra_http_headers={
                    'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"',
                    'accept-language': 'ko-KR,ko;q=0.9,en;q=0.8',
                    'accept-encoding': 'gzip, deflate, br'
                }
            )
            
            # 리소스 차단 설정 적용
            await self._setup_resource_blocking(context)
            
            self.logger.info("크롤링용 컨텍스트 생성 완료")
            return context
            
        except Exception as e:
            self.logger.error(f"크롤링용 컨텍스트 생성 실패: {e}")
            return None
        
    async def _refresh_session(self):
        """세션 리프레시 (쿠키 만료 시)."""
        self.logger.info("세션 리프레시 시작")
        
        if self.page:
            await self.page.close()
        
        # 새 컨텍스트 생성
        self.crawl_context = await self.cookie_manager.refresh_cookies_if_needed(self.crawl_context)
        if not self.crawl_context:
            raise RuntimeError("세션 리프레시 실패")
            
        self.page = await self.crawl_context.new_page()
        self.logger.info("세션 리프레시 완료")
    
    async def _validate_page_content(self, page, goods_no: str) -> bool:
        """
        페이지 내용이 유효한 상품 페이지인지 검사한다.
        
        Args:
            page: Playwright 페이지 인스턴스
            goods_no: 상품 번호 (로깅용)
            
        Returns:
            True if valid product page, False if login/error page
        """
        try:
            # 1. 상품 없음 페이지 감지
            error_element = page.locator('#error-contents.error-page.noProduct')
            if await error_element.count() > 0:
                error_msg = await error_element.locator('#error-contents-head').inner_text() if await error_element.locator('#error-contents-head').count() > 0 else "상품을 찾을 수 없음"
                self.logger.warning(f"Oliveyoung 상품 없음 페이지 감지 ({goods_no}): {error_msg}")
                return False
            
            # 2. 로그인 페이지 감지
            login_element = page.locator('.loginArea.new-loginArea')
            if await login_element.count() > 0:
                self.logger.warning(f"Oliveyoung 로그인 페이지로 리다이렉트됨 ({goods_no}) - 세션 만료 가능성")
                return False
            
            # 3. 일반적인 에러 페이지 감지 (추가 안전장치)
            general_error = page.locator('#error-contents')
            if await general_error.count() > 0:
                self.logger.warning(f"Oliveyoung 에러 페이지 감지 ({goods_no})")
                return False
            
            # 4. 상품 페이지 핵심 요소 존재 확인
            product_name = page.locator('.prd_name')
            if await product_name.count() == 0:
                # 상품명이 없으면 잘못된 페이지일 가능성
                # 하지만 동적 로딩일 수도 있으므로 짧게 대기 후 재확인
                from .utils import random_delay
                await random_delay(2, 3)
                if await product_name.count() == 0:
                    self.logger.warning(f"Oliveyoung 상품명 요소를 찾을 수 없음 ({goods_no}) - 유효하지 않은 페이지")
                    return False
            
            self.logger.debug(f"Oliveyoung 페이지 유효성 검사 통과 ({goods_no})")
            return True
            
        except Exception as e:
            self.logger.error(f"Oliveyoung 페이지 유효성 검사 실패 ({goods_no}): {str(e)}")
            return False
    
    async def _setup_resource_blocking(self, context: BrowserContext) -> None:
        """
        올리브영 전용 리소스 차단 설정 - 상품 이미지 로딩 허용.

        올리브영은 상품 이미지가 로딩되면서 함께 상품 정보도 동적으로 로드되므로
        이미지 로딩을 허용해야 48개 상품이 모두 표시됩니다.

        Args:
            context: 브라우저 컨텍스트
        """
        
        async def handle_route(route):
            """올리브영 전용 리소스 요청 처리"""
            url = route.request.url
            resource_type = route.request.resource_type
            
            # 1. 이미지 리소스 처리 - 올리브영 도메인만 허용
            if resource_type == "image":
                # 올리브영 도메인의 상품 이미지는 허용 (동적 콘텐츠 로딩을 위해 필수)
                if ("oliveyoung.co.kr" in url and 
                    any(keyword in url.lower() for keyword in 
                        ['goods', 'product', 'prd'])):
                    await route.continue_()
                    return
                # 광고 및 추적 이미지는 차단
                elif any(ad_keyword in url.lower() for ad_keyword in 
                         ['ad', 'banner', 'tracking', 'analytics']):
                    await route.abort()
                    return
                # 기타 외부 이미지 차단
                else:
                    await route.abort()
                    return
            
            # 2. 폰트 파일 차단 (성능 향상)
            if (resource_type == "font" or 
                any(ext in url.lower() for ext in 
                    ['.woff', '.woff2', '.ttf', '.otf', '.eot'])):
                await route.abort()
                return
            
            # 3. 미디어 파일 차단 (성능 향상)
            if (resource_type == "media" or 
                any(ext in url.lower() for ext in 
                    ['.mp4', '.avi', '.mov', '.wmv', '.mp3', '.wav', '.ogg'])):
                await route.abort()
                return
            
            # 4. 광고 및 추적 스크립트 차단
            blocked_domains = [
                'google-analytics.com',
                'googletagmanager.com', 
                'facebook.com/tr',
                'doubleclick.net',
                'googlesyndication.com',
                'adsystem.com',
                'ads.yahoo.com',
                'amazon-adsystem.com'
            ]
            
            if any(domain in url.lower() for domain in blocked_domains):
                await route.abort()
                return
            
            # 5. 불필요한 CSS 파일 차단 (일부만)
            if (resource_type == "stylesheet" and 
                any(keyword in url.lower() for keyword in 
                    ['font', 'icon', 'ads'])):
                await route.abort()
                return
            
            # 6. 그 외 요청은 정상 처리 (XHR, fetch, document, script 등)
            await route.continue_()
        
        # 라우터 설정
        await context.route("**/*", handle_route)
        
        self.logger.info(
            "올리브영 전용 리소스 차단 설정 완료 (상품 이미지 로딩 허용)")
        
    async def crawl_single_product(self, goods_no: str) -> Optional[Dict[str, Any]]:
        """
        단일 제품을 크롤링한다.
        
        Args:
            goods_no: 제품의 goodsNo (Oliveyoung 상품 번호)
            
        Returns:
            크롤링된 제품 데이터 또는 None (실패 시)
        """
        async with self.semaphore:
            url = self.PRODUCT_URL_TEMPLATE.format(goodsNo=goods_no)
            
            try:
                
                # 지속적인 컨텍스트에서 새 페이지 생성 (컨텍스트는 닫지 않음)
                if not self.persistent_context:
                    self.persistent_context = await self.create_context()
                    
                # 쿠키 관리자를 통해 컨텍스트 얻기
                if not self.crawl_context:
                    self.crawl_context = await self.cookie_manager.get_crawl_context()
                    if not self.crawl_context:
                        log_error(self.logger, goods_no, "Oliveyoung 크롤링 컨텍스트 생성 실패", None)
                        return None
                
                page = await self.crawl_context.new_page()
                
                # 페이지 로드
                if not await self.safe_goto(page, url):
                    log_error(self.logger, goods_no, "Oliveyoung 페이지 로드 실패", None)
                    await page.close()  # 페이지만 닫기
                    return None
                
                # 페이지 내용 유효성 검사
                if not await self._validate_page_content(page, goods_no):
                    log_error(self.logger, goods_no, "Oliveyoung 유효하지 않은 페이지 (로그인/에러 페이지)", None)
                    await page.close()
                    return None
                
                # 제품 데이터 추출
                product_data = await self._extract_product_data(page, goods_no)
    
                await page.close()
                
                if product_data:
                    self.logger.info(f"Oliveyoung 제품 크롤링 성공: {goods_no} - {product_data['item_name']}")
                else:
                    log_error(self.logger, goods_no, "Oliveyoung 제품 데이터 추출 실패", None)
                
                return product_data

            except Exception as e:
                error_trace = traceback.format_exc()
                log_error(self.logger, goods_no, str(e), error_trace)
                return None
    
    async def crawl_from_branduid_list(
        self, 
        goods_no_list: List[str],
        batch_size: int = 10
    ) -> List[Dict[str, Any]]:
        """
        goodsNo 목록에서 여러 제품을 배치 단위로 크롤링한다.
        
        Args:
            goods_no_list: goodsNo 목록 (Oliveyoung 상품 번호 목록)
            batch_size: 배치 크기 (서버 부담 경감을 위해 기본값 10)
            
        Returns:
            크롤링된 제품 데이터 목록
        """
        try:
            if not goods_no_list:
                self.logger.warning("Oliveyoung goodsNo 목록에서 제품 목록을 찾을 수 없음")
                return []
            
            # 새로운 크롤링 세션 시작 - 기존 저장소 데이터 초기화
            if self.storage:
                self.storage.data = []  # 중복 방지를 위한 내부 데이터 초기화
                self.logger.info("Oliveyoung 저장소 내부 데이터 초기화 완료")
            
            # goodsNo 중복 검사 및 제거
            original_count = len(goods_no_list)
            goods_no_list = list(dict.fromkeys(goods_no_list))  # 순서 유지하며 중복 제거
            if len(goods_no_list) < original_count:
                removed_count = original_count - len(goods_no_list)
                self.logger.info(f"Oliveyoung 중복된 goodsNo {removed_count}개 제거: {original_count} → {len(goods_no_list)}")
            
            self.logger.info(f"Oliveyoung goodsNo 목록에서 {len(goods_no_list)}개 제품 발견 (배치 크기: {batch_size})")
            
            all_products = []
            
            # 배치 단위로 처리
            for i in range(0, len(goods_no_list), batch_size):
                batch = goods_no_list[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (len(goods_no_list) + batch_size - 1) // batch_size
                
                self.logger.info(f"Oliveyoung 배치 {batch_num}/{total_batches} 처리 중 ({len(batch)}개 제품)")
                
                # 각 제품 크롤링 (순차 처리, max_workers=1)
                tasks = [self.crawl_single_product(goods_no) for goods_no in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # 성공한 결과만 필터링
                batch_products = [
                    result for result in results 
                    if isinstance(result, dict) and result is not None
                ]
                
                all_products.extend(batch_products)
                
                # 배치 간 지연 (서버 부담 경감)
                if i + batch_size < len(goods_no_list):  # 마지막 배치가 아닌 경우만
                    from .utils import random_delay
                    await random_delay(5, 7)  # 배치 간 5-7초 지연
                    self.logger.info(f"Oliveyoung 배치 간 지연 완료 (다음 배치: {batch_num + 1}/{total_batches})")
                
            self.logger.info(f"Oliveyoung 전체 크롤링 완료: {len(all_products)}/{len(goods_no_list)}개 성공")
            
            # 크롤링 결과를 저장소에 저장
            if self.storage and all_products:
                for product in all_products:
                    self.storage.add_product(product)
                self.logger.info(f"Oliveyoung {len(all_products)}개 제품 데이터를 저장소에 추가")
            
            return all_products
            
        except Exception as e:
            self.logger.error(f"Oliveyoung 배치 크롤링 실패: {str(e)}")
            return []
    
    async def crawl_all_categories(self, max_items_per_category: int = 15) -> List[Dict[str, Any]]:
        """
        모든 카테고리에서 제품을 크롤링한다.
        
        Args:
            max_items_per_category: 카테고리당 최대 크롤링 개수
            
        Returns:
            크롤링된 제품 데이터 목록
        """
        try:
            # 카테고리 목록 추출
            categories = await self._extract_categories()
            if not categories:
                self.logger.warning("Oliveyoung 카테고리 목록을 찾을 수 없음")
                return []
            
            self.logger.info(f"Oliveyoung {len(categories)}개 카테고리 발견")
            
            all_products = []
            
            for i, category_id in enumerate(categories, 1):
                self.logger.info(f"Oliveyoung 카테고리 {i}/{len(categories)} 처리 중: {category_id}")
                
                # 카테고리별 제품 크롤링
                category_products = await self.crawl_from_category(category_id, max_items_per_category)
                all_products.extend(category_products)
                
                # 카테고리 간 지연 (서버 부담 경감)
                if i < len(categories):  # 마지막 카테고리가 아닌 경우만
                    from .utils import random_delay
                    await random_delay(5, 8)  # 카테고리 간 5-8초 지연
                    self.logger.info(f"Oliveyoung 카테고리 간 지연 완료 (다음: {i + 1}/{len(categories)})")
            
            self.logger.info(f"Oliveyoung 전체 카테고리 크롤링 완료: {len(all_products)}개 제품")
            return all_products
            
        except Exception as e:
            self.logger.error(f"Oliveyoung 전체 카테고리 크롤링 실패: {str(e)}")
            return []
    
    async def crawl_from_category(self, category_id: str, max_items: int = 15) -> List[Dict[str, Any]]:
        """
        특정 카테고리에서 제품을 크롤링한다.
        
        Args:
            category_id: 카테고리 ID
            max_items: 최대 크롤링 개수
            
        Returns:
            크롤링된 제품 데이터 목록
        """
        try:
            # 카테고리 페이지에서 goodsNo 목록 추출
            goods_no_list = await self._extract_goods_no_list_from_category(category_id, max_items)
            
            if not goods_no_list:
                self.logger.warning(f"Oliveyoung 카테고리 {category_id}에서 제품을 찾을 수 없음")
                return []
            
            self.logger.info(f"Oliveyoung 카테고리 {category_id}에서 {len(goods_no_list)}개 제품 발견")
            
            # goodsNo 목록으로 제품 크롤링
            return await self.crawl_from_branduid_list(goods_no_list, batch_size=5)  # 카테고리별로는 배치 크기 작게
            
        except Exception as e:
            self.logger.error(f"Oliveyoung 카테고리 {category_id} 크롤링 실패: {str(e)}")
            return []
    
    async def _extract_categories(self) -> List[str]:
        """메인 페이지에서 카테고리 목록을 추출한다."""
        try:
            if not self.list_page:
                if not self.persistent_context:
                    self.persistent_context = await self.create_context()
                
                self.list_page = await self.persistent_context.new_page()
                await self.safe_goto(self.list_page, self.MAIN_PAGE_URL)
            
            # 카테고리 링크에서 dispCatNo 추출
            category_elements = self.list_page.locator('a[href*="dispCatNo="]')
            category_count = await category_elements.count()
            
            categories = set()  # 중복 제거를 위해 set 사용
            
            for i in range(category_count):
                element = category_elements.nth(i)
                href = await element.get_attribute('href')
                if href and 'dispCatNo=' in href:
                    # dispCatNo 값 추출
                    import re
                    match = re.search(r'dispCatNo=(\d+)', href)
                    if match:
                        categories.add(match.group(1))
            
            category_list = list(categories)
            self.logger.info(f"Oliveyoung {len(category_list)}개 카테고리 추출 완료")
            return category_list
            
        except Exception as e:
            self.logger.error(f"Oliveyoung 카테고리 목록 추출 실패: {str(e)}")
            return []
    
    async def _extract_goods_no_list_from_category(self, category_id: str, max_items: int = 48) -> List[str]:
        """카테고리 페이지에서 goodsNo 목록을 추출한다."""
        try:
            url = self.CATEGORY_URL_TEMPLATE.format(categoryId=category_id)
            
            if not self.persistent_context:
                self.persistent_context = await self.create_context()
                
            page = await self.persistent_context.new_page()
            
            if not await self.safe_goto(page, url):
                await page.close()
                return []
            
            # 페이지 로딩 대기
            from .utils import random_delay
            await random_delay(3, 5)
            
            # 상품 링크에서 goodsNo 추출
            product_links = page.locator('a[href*="goodsNo="]')
            link_count = await product_links.count()
            
            goods_no_list = []
            processed_count = 0
            
            for i in range(min(link_count, max_items * 2)):  # 여유있게 추출 (중복 고려)
                if processed_count >= max_items:
                    break
                    
                link = product_links.nth(i)
                href = await link.get_attribute('href')
                
                if href and 'goodsNo=' in href:
                    # goodsNo 값 추출
                    match = re.search(r'goodsNo=([A-Z0-9]+)', href)
                    if match:
                        goods_no = match.group(1)
                        if goods_no not in goods_no_list:  # 중복 제거
                            goods_no_list.append(goods_no)
                            processed_count += 1
            
            await page.close()
            
            self.logger.info(f"Oliveyoung 카테고리 {category_id}에서 {len(goods_no_list)}개 goodsNo 추출")
            return goods_no_list
            
        except Exception as e:
            self.logger.error(f"Oliveyoung 카테고리 goodsNo 목록 추출 실패: {str(e)}")
            return []
    
    async def _extract_product_data(self, page, goods_no: str) -> Optional[Dict[str, Any]]:
        """
        향상된 API 모니터링이 포함된 제품 데이터 추출.

        추출되는 데이터 필드:
        - goods_no: 제품 번호
        - item_name: 제품명
        - brand_name: 브랜드명
        - price: 판매가
        - origin_price: 원가
        - is_discounted: 할인 여부
        - discount_info: 할인 정보
        - benefit_info: 혜택 정보
        - shipping_info: 배송 정보
        - refund_info: 교환/반품 정보
        - is_soldout: 품절 여부
        - images: 이미지 URL 목록
        - others: 기타 정보
        - option_info: 옵션 정보
        - category_name: 카테고리명
        - category_main: 카테고리 대분류
        - category_sub: 카테고리 중분류
        - category_detail: 카테고리 소분류
        - category_main_id: 카테고리 대분류 ID
        - category_sub_id: 카테고리 중분류 ID
        - category_detail_id: 카테고리 소분류 ID
        - discount_start_date: 할인 시작일
        - discount_end_date: 할인 종료일
        - is_option_available: 옵션 선택 가능 여부
        - unique_item_id: 고유 아이템 ID
        - manufacturer: 제조사/판매처
        - origin_country: 제조국
        - source: 데이터 소스
        - origin_product_url: 원본 제품 URL
    
        Args:
            page: Playwright 페이지 인스턴스
            goods_no: 제품 goodsNo
            
        Returns:
            추출된 제품 데이터 또는 None
        """
        try:
            # 페이지 로딩 대기
            from .utils import random_delay
            await random_delay(2, 4)  # Oliveyoung 안티봇 대응 지연
            
            # 1. 기본 상품 정보 추출
            product_data = await self.product_extractor.extract_basic_info(page, goods_no)
            
            # 2. 가격 정보 추출
            await self.price_extractor.extract_price_info(page, product_data)
            
            # 3. 혜택 정보 추출
            await self.benefit_extractor.extract_benefit_info(page, product_data)
            
            # 4. 이미지 정보 추출
            await self.image_extractor.extract_images(page, product_data)
            
            # 5. 모든 동적 콘텐츠 추출 (향상된 API 모니터링 포함)
            await self.dynamic_extractor.extract_all_dynamic_content(page, product_data)
            
            return product_data
            
        except Exception as e:
            self.logger.error(f"Oliveyoung 제품 데이터 추출 실패 ({goods_no}): {str(e)}")
            return None
    
    def crawl(self, goods_no_list: List[str]) -> List[Dict[str, Any]]:
        """
        동기 방식으로 여러 제품을 크롤링한다.
        
        Args:
            goods_no_list: 크롤링할 goodsNo 목록
            
        Returns:
            크롤링된 제품 데이터 목록
        """
        async def _async_crawl():
            async with self:
                tasks = [self.crawl_single_product(goods_no) for goods_no in goods_no_list]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                products = [
                    result for result in results 
                    if isinstance(result, dict) and result is not None
                ]
                
                return products
        
        return asyncio.run(_async_crawl())
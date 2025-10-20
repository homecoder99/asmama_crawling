"""Oliveyoung 웹사이트 전용 크롤러 구현."""

import asyncio
import os
from typing import Any, Dict, List, Optional
import traceback
import re
import logging

from .cookies import OliveyoungCookieManager
from playwright.async_api import BrowserContext
from .base import BaseCrawler
from .utils import log_error, setup_logger
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
    CATEGORY_URL_TEMPLATE = "https://www.oliveyoung.co.kr/store/display/getMCategoryList.do?dispCatNo={categoryId}"
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
        # 환경변수 OY_LOG_LVL로 로그 레벨 제어 (기본: INFO)
        log_level_str = os.getenv('OY_LOG_LVL', 'INFO').upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        self.logger = setup_logger(__name__, log_level)
        self.semaphore = asyncio.Semaphore(max_workers)  # 동시성 제어
        
        # 데이터 추출기 초기화
        self.product_extractor = OliveyoungProductExtractor(self.logger)
        self.price_extractor = OliveyoungPriceExtractor(self.logger)
        self.benefit_extractor = OliveyoungBenefitExtractor(self.logger)
        self.image_extractor = OliveyoungImageExtractor(self.logger)
        self.dynamic_extractor = OliveyoungDynamicContentExtractor(self.logger)
        
        # 쿠키 관리
        self.cookie_file = cookie_file
        self.cookie_manager = None
        self.crawl_context = None
        self.list_page = None  # 상품 목록 페이지를 계속 열어둘 페이지
        self.current_category_id = None  # 현재 열려있는 카테고리 ID
    
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
        
        # 자동 쿠키 만료 검증 및 컨텍스트 생성
        try:
            self.crawl_context = await self.cookie_manager.ensure_context()
            self.logger.info("Oliveyoung 향상된 크롤러 시작 완료 (자동 쿠키 관리)")
        except Exception as e:
            raise RuntimeError(f"크롤링용 컨텍스트 생성 실패: {e}")
    
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
                
            if self.crawl_context:
                await self.crawl_context.close()
                self.crawl_context = None
                self.logger.info("Oliveyoung 크롤링용 브라우저 컨텍스트 닫기 완료")

            if self.cookie_manager:
                await self.cookie_manager.stop()
                self.cookie_manager = None
                self.logger.info("Oliveyoung 쿠키 매니저 종료 완료")

            if self.list_page:
                await self.list_page.close()
                self.list_page = None
                self.logger.info("Oliveyoung 상품 목록 페이지 닫기 완료")

        except Exception as e:
            self.logger.error(f"Oliveyoung 지속적인 리소스 정리 중 오류: {str(e)}")
        
        await super().stop()
        
    async def _refresh_session(self):
        """세션 리프레시 (쿠키 만료 시)."""
        self.logger.info("세션 리프레시 시작")
        
        if self.page:
            await self.page.close()
        
        # 기존 컨텍스트 정리 후 새 컨텍스트 생성
        if self.crawl_context:
            await self.crawl_context.close()
            self.crawl_context = None
        
        try:
            self.crawl_context = await self.cookie_manager.ensure_context()
        except Exception as e:
            raise RuntimeError(f"세션 리프레시 실패: {e}")
            
        self.page = await self.crawl_context.new_page()
        self.logger.info("세션 리프레시 완료")
    
    async def ensure_list_page(self, category_id: str, rows_per_page: int = 1000, sort_type: str = "01") -> bool:
        """
        카테고리 목록 페이지를 지속적으로 유지한다.

        카테고리가 변경되거나 페이지가 없으면 새로 생성하고,
        동일한 카테고리면 기존 페이지를 재사용한다.

        Args:
            category_id: 카테고리 ID
            rows_per_page: 페이지당 표시할 아이템 수 (기본값: 1000)
            sort_type: 정렬 타입 (01=판매순, 02=최신순)

        Returns:
            페이지 준비 성공 여부
        """
        try:
            # 카테고리가 변경되거나 페이지가 없으면 새로 생성
            if (not self.list_page or
                self.current_category_id != category_id or
                self.list_page.is_closed()):

                # 기존 페이지가 있으면 닫기
                if self.list_page and not self.list_page.is_closed():
                    await self.list_page.close()
                    self.logger.info(f"이전 카테고리 페이지 닫기: {self.current_category_id}")

                # 컨텍스트 확인
                if not self.crawl_context:
                    try:
                        self.crawl_context = await self.cookie_manager.ensure_context()
                    except Exception as e:
                        self.logger.error(f"크롤링 컨텍스트 생성 실패: {e}")
                        return False

                # 새 카테고리 페이지 생성
                self.list_page = await self.crawl_context.new_page()

                # 카테고리 URL 생성 및 이동 (rowsPerPage, prdSort 파라미터 추가)
                category_url = f"{self.CATEGORY_URL_TEMPLATE.format(categoryId=category_id)}&prdSort={sort_type}&rowsPerPage={rows_per_page}"

                self.logger.info(f"카테고리 페이지 이동: {category_url}")

                if not await self.safe_goto(self.list_page, category_url):
                    await self.list_page.close()
                    self.list_page = None
                    return False

                # 페이지 로딩 대기
                from .utils import random_delay
                await random_delay(0.5, 1.5)

                self.current_category_id = category_id
                self.logger.info(f"카테고리 목록 페이지 준비 완료: {category_id}")
            else:
                self.logger.debug(f"기존 카테고리 페이지 재사용: {category_id}")

            return True

        except Exception as e:
            self.logger.error(f"카테고리 목록 페이지 준비 실패: {e}")
            if self.list_page and not self.list_page.is_closed():
                await self.list_page.close()
            self.list_page = None
            self.current_category_id = None
            return False
    
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
            # 0. Cloudflare 봇 차단 페이지 감지
            page_content = await page.content()
            
            # Cloudflare 에러 페이지 특징 검사
            cloudflare_indicators = [
                '페이지를 제대로 표시할 수 없어요',
            ]
            
            if any(indicator in page_content for indicator in cloudflare_indicators):
                self.logger.error(f"Oliveyoung Cloudflare 봇 차단 페이지 감지 ({goods_no}) - anti-bot 대응 필요")
                return False
            
            # 1. 상품 없음 페이지 감지
            error_element = page.locator('#error-contents.error-page.noProduct')
            if await error_element.count() > 0:
                error_msg = await error_element.locator('#error-contents-head').inner_text() if await error_element.locator('#error-contents-head').count() > 0 else "상품을 찾을 수 없음"
                self.logger.warning(f"Oliveyoung 상품 없음 페이지 감지 ({goods_no}): {error_msg}")
                return False
            
            # 2. 로그인 페이지 감지
            login_element = page.locator('.loginArea.new-loginArea')
            if await login_element.count() > 0:
                self.logger.warning(f"Oliveyoung 로그인 페이지 감지({goods_no}) - 세션 만료 또는 성인 물품")  
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
                await random_delay(0.5, 1.5)
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
                # 쿠키 만료 검증 후 자동 재생성
                if not self.crawl_context:
                    try:
                        self.crawl_context = await self.cookie_manager.ensure_context()
                    except Exception as e:
                        log_error(self.logger, goods_no, f"Oliveyoung 크롤링 컨텍스트 생성 실패: {e}", None)
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
                    await random_delay(1, 2)  # 배치 간 1-2초 지연
                    self.logger.info(f"Oliveyoung 배치 간 지연 완료 (다음 배치: {batch_num + 1}/{total_batches})")
                
            self.logger.info(f"Oliveyoung 전체 크롤링 완료: {len(all_products)}/{len(goods_no_list)}개 성공")
            
            # 크롤링 결과를 저장소에 저장
            if self.storage and all_products:
                self.storage.save(all_products)
                self.logger.info(f"Oliveyoung {len(all_products)}개 제품 데이터를 저장소에 저장")
            
            return all_products
            
        except Exception as e:
            self.logger.error(f"Oliveyoung 배치 크롤링 실패: {str(e)}")
            return []
    
    async def crawl_all_categories(self, max_items_per_category: int = 15, category_filter: List[str] = None) -> List[Dict[str, Any]]:
        """
        모든 카테고리에서 제품을 크롤링한다.
        
        Args:
            max_items_per_category: 카테고리당 최대 크롤링 개수
            category_filter: 포함할 카테고리 이름 목록 (None이면 모든 카테고리)
            
        Returns:
            크롤링된 제품 데이터 목록
        """
        try:
            # 카테고리 목록 추출 (ID와 이름 포함)
            all_categories = await self.extract_all_category_ids()
            if not all_categories:
                self.logger.warning("Oliveyoung 카테고리 목록을 찾을 수 없음")
                return []
            
            # 카테고리 필터링
            if category_filter:
                filtered_categories = []
                filter_lower = [name.lower() for name in category_filter]
                
                for category in all_categories:
                    # 현재 카테고리가 필터 목록에 있으면 건너뛴다
                    if category["name"].strip().lower() in filter_lower:
                        continue
                    filtered_categories.append(category)
                
                categories = filtered_categories
                self.logger.info(f"카테고리 필터링 적용: {len(all_categories)}개 → {len(categories)}개")
                
                # 필터링된 카테고리 로깅
                for category in categories:
                    self.logger.info(f"  - {category['id']}: {category['name']}")
            else:
                categories = all_categories
            
            if not categories:
                self.logger.warning("필터링 후 크롤링할 카테고리가 없음")
                return []
            
            self.logger.info(f"Oliveyoung {len(categories)}개 카테고리에서 크롤링 시작")
            
            all_products = []
            
            for i, category in enumerate(categories, 1):
                category_id = category["id"]
                category_name = category["name"]
                
                self.logger.info(f"Oliveyoung 카테고리 {i}/{len(categories)} 처리 중: {category_id} ({category_name})")
                
                # 카테고리별 제품 크롤링
                category_products = await self.crawl_from_category(
                    category_id, max_items_per_category
                )
                all_products.extend(category_products)
                
                # 카테고리 간 지연 (서버 부담 경감)
                if i < len(categories):  # 마지막 카테고리가 아닌 경우만
                    from .utils import random_delay
                    await random_delay(1, 2)  # 카테고리 간 1-2초 지연
                    self.logger.info(f"Oliveyoung 카테고리 간 지연 완료 (다음: {i + 1}/{len(categories)})")
            
            self.logger.info(f"Oliveyoung 전체 카테고리 크롤링 완료: {len(all_products)}개 제품")
            return all_products
            
        except Exception as e:
            self.logger.error(f"Oliveyoung 전체 카테고리 크롤링 실패: {str(e)}")
            return []
    
    async def crawl_from_category(self, category_id: str, max_items: int = 15, sort_type: str = "01") -> List[Dict[str, Any]]:
        """
        특정 카테고리에서 제품을 크롤링한다.

        Args:
            category_id: 카테고리 ID
            max_items: 최대 크롤링 개수
            sort_type: 정렬 타입 (01=판매순, 02=최신순)

        Returns:
            크롤링된 제품 데이터 목록
        """
        try:
            # 카테고리 페이지에서 goodsNo 목록 추출
            goods_no_list = await self._extract_goods_no_list_from_category(category_id, max_items, sort_type)

            if not goods_no_list:
                self.logger.warning(f"Oliveyoung 카테고리 {category_id}에서 제품을 찾을 수 없음")
                return []

            self.logger.info(f"Oliveyoung 카테고리 {category_id}에서 {len(goods_no_list)}개 제품 발견")

            # goodsNo 목록으로 제품 크롤링
            return await self.crawl_from_branduid_list(goods_no_list, batch_size=5)  # 카테고리별로는 배치 크기 작게

        except Exception as e:
            self.logger.error(f"Oliveyoung 카테고리 {category_id} 크롤링 실패: {str(e)}")
            return []

    async def crawl_new_products_only(
        self,
        existing_excel_path: str,
        max_items_per_category: int = 15,
        category_filter: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        기존 크롤링 결과와 비교하여 최신 상품만 크롤링한다.

        Args:
            existing_excel_path: 기존 크롤링 결과 엑셀 파일 경로
            max_items_per_category: 카테고리당 최대 크롤링 개수
            category_filter: 제외할 카테고리 이름 목록 (None이면 모든 카테고리)

        Returns:
            크롤링된 신규 제품 데이터 목록
        """
        try:
            # 1. 기존 엑셀에서 goods_no 목록 추출
            self.logger.info(f"기존 크롤링 결과 로드: {existing_excel_path}")

            import pandas as pd
            from pathlib import Path

            excel_path = Path(existing_excel_path)
            if not excel_path.exists():
                self.logger.error(f"기존 크롤링 결과 파일을 찾을 수 없음: {existing_excel_path}")
                return []

            existing_df = pd.read_excel(existing_excel_path)

            if 'goods_no' not in existing_df.columns:
                self.logger.error(f"엑셀 파일에 'goods_no' 칼럼이 없음: {existing_excel_path}")
                return []

            existing_goods_no_set = set(existing_df['goods_no'].dropna().astype(str))
            self.logger.info(f"기존 크롤링 결과: {len(existing_goods_no_set)}개 상품")

            # 2. 카테고리 목록 추출 및 필터링
            all_categories = await self.extract_all_category_ids()
            if not all_categories:
                self.logger.warning("Oliveyoung 카테고리 목록을 찾을 수 없음")
                return []

            if category_filter:
                filtered_categories = []
                filter_lower = [name.lower() for name in category_filter]

                for category in all_categories:
                    if category["name"].strip().lower() in filter_lower:
                        continue
                    filtered_categories.append(category)

                categories = filtered_categories
                self.logger.info(f"카테고리 필터링 적용: {len(all_categories)}개 → {len(categories)}개")
            else:
                categories = all_categories

            if not categories:
                self.logger.warning("필터링 후 크롤링할 카테고리가 없음")
                return []

            # 3. 각 카테고리에서 최신 상품 목록 추출 (prdSort=02)
            self.logger.info(f"Oliveyoung {len(categories)}개 카테고리에서 최신 상품 크롤링 시작")

            all_new_goods_no = []

            for i, category in enumerate(categories, 1):
                category_id = category["id"]
                category_name = category["name"]

                self.logger.info(f"카테고리 {i}/{len(categories)} 처리 중: {category_id} ({category_name})")

                # 카테고리에서 최신순 정렬로 goods_no 추출
                goods_no_list = await self._extract_goods_no_list_from_category(
                    category_id, max_items_per_category, sort_type="02"  # 최신순
                )

                if not goods_no_list:
                    self.logger.warning(f"카테고리 {category_id}에서 상품을 찾을 수 없음")
                    continue

                # 기존 데이터와 비교하여 신규 상품만 필터링
                new_goods_no = [
                    goods_no for goods_no in goods_no_list
                    if goods_no not in existing_goods_no_set
                ]

                self.logger.info(
                    f"카테고리 {category_id}: {len(goods_no_list)}개 최신 상품 중 "
                    f"{len(new_goods_no)}개 신규 상품 발견"
                )

                all_new_goods_no.extend(new_goods_no)

                # 카테고리 간 지연
                if i < len(categories):
                    from .utils import random_delay
                    await random_delay(1, 2)

            # 4. 신규 상품 크롤링
            if not all_new_goods_no:
                self.logger.info("신규 상품이 없습니다.")
                return []

            self.logger.info(f"총 {len(all_new_goods_no)}개 신규 상품 크롤링 시작")

            # 중복 제거
            unique_new_goods_no = list(dict.fromkeys(all_new_goods_no))
            if len(unique_new_goods_no) < len(all_new_goods_no):
                self.logger.info(
                    f"중복 제거: {len(all_new_goods_no)}개 → {len(unique_new_goods_no)}개"
                )

            # 배치 크롤링
            new_products = await self.crawl_from_branduid_list(
                unique_new_goods_no, batch_size=10
            )

            self.logger.info(
                f"신규 상품 크롤링 완료: {len(new_products)}/{len(unique_new_goods_no)}개 성공"
            )

            return new_products

        except Exception as e:
            self.logger.error(f"���신 상품 크롤링 실패: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []
    

    async def extract_all_category_ids(self) -> List[Dict[str, str]]:
        """
        메인 페이지에서 모든 카테고리 ID와 이름을 추출한다.
        
        data-ref-dispcatno 속성과 내부 텍스트를 추출하여 전체 카테고리 트리를 가져온다.
        
        Returns:
            카테고리 정보 리스트 [{"id": "category_id", "name": "category_name"}]
        """
        try:
            # 컨텍스트 확인
            if not self.crawl_context:
                try:
                    self.crawl_context = await self.cookie_manager.ensure_context()
                except Exception as e:
                    self.logger.error(f"크롤링 컨텍스트 생성 실패: {e}")
                    return []
            
            # 메인 페이지 전용 페이지 생성 (기존 list_page와 분리)
            main_page = await self.crawl_context.new_page()
            
            try:
                self.logger.info(f"메인 페이지로 이동: {self.MAIN_PAGE_URL}")
                
                if not await self.safe_goto(main_page, self.MAIN_PAGE_URL):
                    self.logger.error("메인 페이지 로드 실패")
                    return []
                
                # 페이지 로딩 대기
                from .utils import random_delay
                await random_delay(2, 3)
                
                # 메인 메뉴 내의 카테고리 링크만 선택 (더 정확한 선택자 사용)
                # 메인 카테고리 (대분류): #gnbAllMenu .all_menu_wrap .sub_menu_box .sub_depth > a[data-ref-dispcatno]
                # 서브 카테고리 (중/소분류): #gnbAllMenu .all_menu_wrap .sub_menu_box ul > li > a[data-ref-dispcatno]
                main_category_selector = '#gnbAllMenu .all_menu_wrap .sub_menu_box .sub_depth > a[data-ref-dispcatno]'
                sub_category_selector = '#gnbAllMenu .all_menu_wrap .sub_menu_box ul > li > a[data-ref-dispcatno]'
                
                # 메인 카테고리 요소들 추출
                main_category_elements = main_page.locator(main_category_selector)
                main_count = await main_category_elements.count()
                
                # 서브 카테고리 요소들 추출
                sub_category_elements = main_page.locator(sub_category_selector)
                sub_count = await sub_category_elements.count()
                
                total_count = main_count + sub_count
                self.logger.info(f"카테고리 링크 발견: 메인 {main_count}개, 서브 {sub_count}개, 총 {total_count}개")
                
                categories = {}  # 중복 제거를 위해 dict 사용 (id: name)
                
                # 메인 카테고리 처리
                for i in range(main_count):
                    try:
                        element = main_category_elements.nth(i)
                        cat_id = await element.get_attribute('data-ref-dispcatno')
                        
                        if cat_id and cat_id.strip() and cat_id.isdigit():
                            # 15자리 카테고리 ID만 추출
                            if len(cat_id) == 15:
                                cat_name = await element.inner_text()
                                cat_name = cat_name.strip() if cat_name else ""
                                
                                if cat_name:  # 카테고리 이름이 있는 경우만 추가
                                    categories[cat_id.strip()] = cat_name
                                    self.logger.debug(f"메인 카테고리 추가: {cat_id} - {cat_name}")

                    except Exception as e:
                        self.logger.debug(f"메인 카테고리 요소 {i} 처리 중 오류: {e}")
                        continue
                
                # 서브 카테고리 처리
                for i in range(sub_count):
                    try:
                        element = sub_category_elements.nth(i)
                        cat_id = await element.get_attribute('data-ref-dispcatno')
                        
                        if cat_id and cat_id.strip() and cat_id.isdigit():
                            # 15자리 카테고리 ID만 추출
                            if len(cat_id) == 15:
                                cat_name = await element.inner_text()
                                cat_name = cat_name.strip() if cat_name else ""
                                
                                if cat_name:  # 카테고리 이름이 있는 경우만 추가
                                    categories[cat_id.strip()] = cat_name
                                    self.logger.debug(f"서브 카테고리 추가: {cat_id} - {cat_name}")

                    except Exception as e:
                        self.logger.debug(f"서브 카테고리 요소 {i} 처리 중 오류: {e}")
                        continue

                # dict를 list of dict로 변환하고 ID순으로 정렬
                category_list = [{"id": cat_id, "name": cat_name} 
                               for cat_id, cat_name in sorted(categories.items())]
                
                self.logger.info(f"전체 카테고리 {len(category_list)}개 추출 완료")
                
                # 카테고리 구조 분석 로깅
                by_length = {}
                for category in category_list:
                    cat_id = category["id"]
                    length = len(cat_id)
                    if length not in by_length:
                        by_length[length] = []
                    by_length[length].append(f"{cat_id}({category['name']})")
                
                self.logger.info("카테고리 구조:")
                for length in sorted(by_length.keys()):
                    count = len(by_length[length])
                    examples = ', '.join(by_length[length][:3])
                    if count > 3:
                        examples += '...'
                    self.logger.info(f"  길이 {length:2d}자리: {count:3d}개 - {examples}")
                
                return category_list
                
            finally:
                await main_page.close()
                
        except Exception as e:
            self.logger.error(f"전체 카테고리 ID 추출 실패: {str(e)}")
            return []
    
    async def _extract_categories(self) -> List[str]:
        """기존 메서드 호환성을 위한 래퍼. 카테고리 ID만 반환."""
        categories = await self.extract_all_category_ids()
        return [category["id"] for category in categories]
    
    async def _extract_goods_no_list_from_category(self, category_id: str, max_items: int = 48, sort_type: str = "01") -> List[str]:
        """
        카테고리 페이지에서 goodsNo 목록을 추출한다.
        지속적인 list_page를 사용하여 효율성을 높인다.

        Args:
            category_id: 카테고리 ID
            max_items: 최대 아이템 수
            sort_type: 정렬 타입 (01=판매순, 02=최신순)
        """
        try:
            # 카테고리 목록 페이지 준비 (지속적으로 유지) - sort_type 추가
            if not await self.ensure_list_page(category_id, max_items, sort_type):
                self.logger.error(f"카테고리 페이지 준비 실패: {category_id}")
                return []

            # 상품 링크에서 goodsNo 추출
            product_links = self.list_page.locator('a[href*="goodsNo="]')
            link_count = await product_links.count()

            goods_no_list = []
            processed_count = 0

            self.logger.info(f"카테고리 {category_id}에서 {link_count}개 상품 링크 발견")

            for i in range(min(link_count, max_items * 2)):  # 여유있게 추출 (중복 고려)
                if processed_count >= max_items:
                    break

                try:
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

                except Exception as e:
                    self.logger.debug(f"상품 링크 {i} 처리 중 오류: {e}")
                    continue

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
            await random_delay(0.5, 1.5)  # Oliveyoung 안티봇 대응 지연
            
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
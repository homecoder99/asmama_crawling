"""크롤러 베이스 클래스 정의."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
import logging
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from .utils import get_random_user_agent, get_random_viewport, random_delay, log_error


class BaseCrawler(ABC):
    """
    모든 크롤러가 상속받을 추상 베이스 클래스.
    
    Playwright를 사용한 웹 크롤링의 공통 기능을 제공한다.
    """
    
    def __init__(self, storage: Any = None, max_workers: int = 3):
        """
        베이스 크롤러를 초기화한다.
        
        Args:
            storage: 데이터 저장소 인스턴스
            max_workers: 최대 동시 세션 수
        """
        self.storage = storage
        self.max_workers = max_workers
        
        # 로거 설정 - setup_logger와 동일한 핸들러 사용
        from .utils import setup_logger
        self.logger = setup_logger(self.__class__.__name__)
        
        # Playwright 관련 변수
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.contexts: List[BrowserContext] = []
        
    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입."""
        await self.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료."""
        await self.stop()
        
    async def start(self) -> None:
        """
        크롤러를 시작하고 브라우저를 초기화한다.
        """
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=False,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            self.logger.info("브라우저 초기화 완료")
        except Exception as e:
            self.logger.error(f"브라우저 초기화 실패: {str(e)}")
            raise
            
    async def stop(self) -> None:
        """
        크롤러를 종료하고 리소스를 정리한다.
        """
        try:
            # 모든 컨텍스트 정리
            for context in self.contexts:
                await context.close()
            self.contexts.clear()
            
            if self.browser:
                await self.browser.close()
                
            if self.playwright:
                await self.playwright.stop()
                
            self.logger.info("크롤러 종료 완료")
        except Exception as e:
            self.logger.error(f"크롤러 종료 중 오류: {str(e)}")
            
    async def create_context(self) -> BrowserContext:
        """
        새로운 브라우저 컨텍스트를 생성하고 리소스 차단을 설정한다.
        
        Returns:
            생성된 브라우저 컨텍스트
        """
        if not self.browser:
            raise RuntimeError("브라우저가 초기화되지 않았습니다.")
            
        viewport = get_random_viewport()
        user_agent = get_random_user_agent()
        
        context = await self.browser.new_context(
            viewport=viewport,
            user_agent=user_agent
        )
        
        # 서버 부담 경감을 위한 리소스 차단 설정
        await self._setup_resource_blocking(context)
        
        self.contexts.append(context)
        return context
    
    async def _setup_resource_blocking(self, context: BrowserContext) -> None:
        """
        서버 부담 경감을 위한 리소스 차단을 설정한다.
        
        Args:
            context: 브라우저 컨텍스트
        """
        async def handle_route(route):
            """리소스 요청을 처리한다."""
            url = route.request.url
            resource_type = route.request.resource_type
            
            # 이미지 파일 차단 (URL은 수집하되 실제 다운로드 방지)
            if resource_type == "image":
                await route.abort()
                return
            
            # 폰트 파일 차단
            if resource_type == "font" or any(ext in url.lower() for ext in ['.woff', '.woff2', '.ttf', '.otf', '.eot']):
                await route.abort()
                return
            
            # 미디어 파일 차단
            if resource_type == "media" or any(ext in url.lower() for ext in ['.mp4', '.avi', '.mov', '.wmv', '.mp3', '.wav', '.ogg']):
                await route.abort()
                return
            
            # 광고 및 추적 스크립트 차단
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
            
            # 불필요한 CSS 파일 차단 (일부만)
            if resource_type == "stylesheet" and any(keyword in url.lower() for keyword in ['font', 'icon', 'ads']):
                await route.abort()
                return
            
            # 그 외 요청은 정상 처리
            await route.continue_()
        
        # 라우터 설정
        await context.route("**/*", handle_route)
        
        self.logger.debug("리소스 차단 설정 완료 (이미지, 폰트, 미디어, 광고 스크립트)")
        
    async def create_page(self, context: Optional[BrowserContext] = None) -> Page:
        """
        새로운 페이지를 생성한다.
        
        Args:
            context: 브라우저 컨텍스트 (없으면 새로 생성)
            
        Returns:
            생성된 페이지
        """
        if context is None:
            context = await self.create_context()
            
        page = await context.new_page()
        return page
        
    async def safe_goto(self, page: Page, url: str, timeout: int = 60000) -> bool:
        """
        안전하게 페이지로 이동한다.
        
        Args:
            page: 페이지 인스턴스
            url: 이동할 URL
            timeout: 타임아웃 (밀리초, 기본값 60초)
            
        Returns:
            성공 여부
        """
        try:
            await page.goto(url, timeout=timeout, wait_until='domcontentloaded')
            await random_delay()
            return True
        except Exception as e:
            self.logger.warning(f"페이지 이동 실패 ({url}): {str(e)}")
            return False
            
    async def safe_wait_for_selector(
        self, 
        page: Page, 
        selector: str, 
        timeout: int = 10000
    ) -> bool:
        """
        안전하게 셀렉터를 기다린다.
        
        Args:
            page: 페이지 인스턴스
            selector: CSS 셀렉터
            timeout: 타임아웃 (밀리초)
            
        Returns:
            요소가 발견되었는지 여부
        """
        try:
            await page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception:
            return False
            
    async def safe_get_text(self, page: Page, selector: str) -> Optional[str]:
        """
        안전하게 텍스트를 추출한다.
        
        Args:
            page: 페이지 인스턴스
            selector: CSS 셀렉터
            
        Returns:
            추출된 텍스트 또는 None
        """
        try:
            element = await page.query_selector(selector)
            return await element.inner_text() if element else None
        except Exception:
            return None
            
    async def safe_get_attribute(
        self, 
        page: Page, 
        selector: str, 
        attribute: str
    ) -> Optional[str]:
        """
        안전하게 속성값을 추출한다.
        
        Args:
            page: 페이지 인스턴스
            selector: CSS 셀렉터
            attribute: 속성명
            
        Returns:
            속성값 또는 None
        """
        try:
            element = await page.query_selector(selector)
            return await element.get_attribute(attribute) if element else None
        except Exception:
            return None
            
    async def retry_operation(
        self, 
        operation, 
        max_retries: int = 3, 
        delay: float = 1.0
    ) -> Any:
        """
        재시도 로직으로 작업을 실행한다.
        
        Args:
            operation: 실행할 비동기 함수
            max_retries: 최대 재시도 횟수
            delay: 재시도 간격(초)
            
        Returns:
            작업 결과
            
        Raises:
            마지막 시도에서 발생한 예외
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                return await operation()
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    self.logger.warning(f"작업 실패 (시도 {attempt + 1}/{max_retries + 1}): {str(e)}")
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(f"모든 재시도 실패: {str(e)}")
                    
        raise last_exception
        
    @abstractmethod
    async def crawl_single_product(self, identifier: str) -> Optional[Dict[str, Any]]:
        """
        단일 제품을 크롤링한다.
        
        Args:
            identifier: 제품 식별자
            
        Returns:
            크롤링된 제품 데이터 또는 None
        """
        pass
        
    @abstractmethod
    async def crawl_from_branduid_list(
        self, 
        branduid_list: List[str],
        batch_size: int = 15
    ) -> List[Dict[str, Any]]:
        """
        branduid 목록에서 여러 제품을 크롤링한다.
        
        Args:
            branduid_list: branduid 목록
            batch_size: 배치 크기 (서버 부담 경감을 위해 기본값 15)
            
        Returns:
            크롤링된 제품 데이터 목록
        """
        pass
        
    def save_data(self, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> None:
        """
        데이터를 저장한다.
        
        Args:
            data: 저장할 데이터 (단일 또는 리스트)
        """
        if self.storage:
            self.storage.save(data)
        else:
            self.logger.warning("저장소가 설정되지 않음")
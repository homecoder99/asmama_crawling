"""올리브영 쿠키 발급 및 관리 시스템."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright

# 로깅 설정
logger = logging.getLogger(__name__)


class OliveyoungCookieManager:
    """올리브영 Cloudflare 쿠키 발급 및 관리를 담당하는 클래스."""
    
    # 고정 User-Agent (일관성 유지)
    FIXED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    # 필수 쿠키 목록
    REQUIRED_COOKIES = ['cf_clearance', '__cf_bm', 'OYSESSIONID']
    
    # 올리브영 URL
    BOOTSTRAP_URL = "https://www.oliveyoung.co.kr/store/main/main.do"
    
    def __init__(self, cookie_file: str = "oy_state.json"):
        """
        쿠키 매니저 초기화.
        
        Args:
            cookie_file: 쿠키 저장 파일 경로
        """
        self.cookie_file = Path(cookie_file)
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        
    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입."""
        await self.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료."""
        await self.stop()
        
    async def start(self):
        """Playwright 및 브라우저 초기화."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=False,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-features=VizDisplayCompositor'
            ]
        )
        logger.info("올리브영 쿠키 매니저 초기화 완료")
        
    async def stop(self):
        """리소스 정리."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("올리브영 쿠키 매니저 종료 완료")
    
    async def bootstrap_cookies(self) -> bool:
        """
        Cloudflare 챌린지를 통과하여 쿠키를 발급받는다.
        
        Returns:
            쿠키 발급 성공 여부
        """
        logger.info("올리브영 쿠키 부트스트랩 시작")
        
        try:
            # 리소스 차단 없는 컨텍스트 생성
            context = await self.browser.new_context(
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
            
            page = await context.new_page()
            
            # 메인 페이지 접속 (Cloudflare 챌린지 통과)
            logger.info(f"올리브영 메인 페이지 접속: {self.BOOTSTRAP_URL}")
            response = await page.goto(
                self.BOOTSTRAP_URL, 
                wait_until="networkidle",
                timeout=60000
            )
            
            logger.info(f"페이지 응답 상태: {response.status}")
            
            # Cloudflare 챌린지 대기 (최대 30초)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
                await asyncio.sleep(5)  # 추가 안정화 대기
            except Exception as e:
                logger.warning(f"Cloudflare 챌린지 대기 중 오류: {e}")
            
            # 쿠키 확인
            cookies = await context.cookies()
            cookie_names = [cookie['name'] for cookie in cookies]
            
            logger.info(f"획득한 쿠키 목록: {cookie_names}")
            
            # 필수 쿠키 확인
            missing_cookies = [name for name in self.REQUIRED_COOKIES if name not in cookie_names]
            
            if missing_cookies:
                logger.warning(f"누락된 필수 쿠키: {missing_cookies}")
                
                # Cloudflare 쿠키가 없어도 세션 쿠키라도 있으면 진행
                if 'OYSESSIONID' in cookie_names:
                    logger.info("세션 쿠키(OYSESSIONID)가 있어 진행합니다")
                else:
                    logger.error("필수 세션 쿠키도 없습니다")
                    await context.close()
                    return False
            else:
                logger.info("모든 필수 쿠키 획득 완료")
            
            # 쿠키 상태 저장
            await context.storage_state(path=str(self.cookie_file))
            logger.info(f"쿠키 상태 저장 완료: {self.cookie_file}")
            
            await context.close()
            return True
            
        except Exception as e:
            logger.error(f"쿠키 부트스트랩 실패: {e}")
            return False
    
    async def get_crawl_context(self) -> Optional[BrowserContext]:
        """
        크롤링용 컨텍스트를 생성한다 (저장된 쿠키 로드).
        
        Returns:
            크롤링용 브라우저 컨텍스트 또는 None
        """
        if not self.cookie_file.exists():
            logger.error(f"쿠키 파일이 존재하지 않습니다: {self.cookie_file}")
            return None
            
        try:
            logger.info(f"저장된 쿠키 상태 로드: {self.cookie_file}")
            
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
            
            logger.info("크롤링용 컨텍스트 생성 완료")
            return context
            
        except Exception as e:
            logger.error(f"크롤링용 컨텍스트 생성 실패: {e}")
            return None
    
    async def _setup_resource_blocking(self, context: BrowserContext) -> None:
        """
        올리브영 전용 리소스 차단 설정.
        
        Args:
            context: 브라우저 컨텍스트
        """
        # 필수 API 화이트리스트
        ESSENTIAL_XHR = (
            "/getGoodsArtcAjax.do",
            "/getOptInfoListAjax.do",
        )
        
        async def handle_route(route):
            """리소스 요청 처리"""
            url = route.request.url
            resource_type = route.request.resource_type
            
            # 1. 필수 API 화이트리스트 - 최우선 통과
            if any(essential_api in url for essential_api in ESSENTIAL_XHR):
                logger.debug(f"필수 API 통과: {url}")
                await route.continue_()
                return
            
            # 2. 이미지 리소스 처리 - 올리브영 도메인만 허용
            if resource_type == "image":
                if ("oliveyoung.co.kr" in url and 
                    any(keyword in url.lower() for keyword in ['goods', 'product', 'prd'])):
                    await route.continue_()
                    return
                else:
                    await route.abort()
                    return
            
            # 3. 폰트, 미디어 파일 차단
            if (resource_type in ["font", "media"] or 
                any(ext in url.lower() for ext in 
                    ['.woff', '.woff2', '.ttf', '.otf', '.eot', 
                     '.mp4', '.avi', '.mov', '.wmv', '.mp3', '.wav', '.ogg'])):
                await route.abort()
                return
            
            # 4. 광고 및 추적 스크립트 차단
            blocked_domains = [
                'google-analytics.com', 'googletagmanager.com', 'facebook.com/tr',
                'doubleclick.net', 'googlesyndication.com', 'adsystem.com'
            ]
            
            if any(domain in url.lower() for domain in blocked_domains):
                await route.abort()
                return
            
            # 5. 그 외 요청은 정상 처리
            await route.continue_()
        
        await context.route("**/*", handle_route)
        logger.info("리소스 차단 설정 완료")
    
    async def refresh_cookies_if_needed(self, context: Optional[BrowserContext] = None) -> Optional[BrowserContext]:
        """
        필요시 쿠키를 리프레시하고 새 컨텍스트를 반환한다.
        
        Args:
            context: 현재 컨텍스트 (있으면 닫음)
            
        Returns:
            새로운 크롤링용 컨텍스트 또는 None
        """
        if context:
            await context.close()
            logger.info("기존 컨텍스트 종료")
        
        logger.info("쿠키 리프레시 시작")
        
        # 쿠키 재발급
        if await self.bootstrap_cookies():
            # 새 컨텍스트 생성
            new_context = await self.get_crawl_context()
            if new_context:
                logger.info("쿠키 리프레시 및 새 컨텍스트 생성 완료")
                return new_context
        
        logger.error("쿠키 리프레시 실패")
        return None


# 편의 함수들
async def bootstrap_cookies(cookie_file: str = "oy_state.json") -> bool:
    """
    쿠키 부트스트랩 편의 함수.
    
    Args:
        cookie_file: 쿠키 저장 파일 경로
        
    Returns:
        성공 여부
    """
    async with OliveyoungCookieManager(cookie_file) as manager:
        return await manager.bootstrap_cookies()


async def get_crawl_context(cookie_file: str = "oy_state.json") -> Optional[BrowserContext]:
    """
    크롤링용 컨텍스트 생성 편의 함수.
    
    Args:
        cookie_file: 쿠키 파일 경로
        
    Returns:
        크롤링용 컨텍스트 또는 None
    """
    manager = OliveyoungCookieManager(cookie_file)
    await manager.start()
    
    try:
        return await manager.get_crawl_context()
    except Exception as e:
        logger.error(f"컨텍스트 생성 실패: {e}")
        await manager.stop()
        return None
"""올리브영 쿠키 발급 및 관리 시스템."""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright
from filelock import FileLock

from .utils import setup_logger

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
        
        # 디렉토리 선처리
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        
        # 환경변수 OY_LOG_LVL로 로거 레벨 제어
        log_level_str = os.getenv('OY_LOG_LVL', 'INFO').upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        self.logger = setup_logger(__name__, log_level)
        
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
        
        # 환경변수 OY_DEBUG로 headless 모드 제어
        is_headless = False # os.getenv('OY_DEBUG')
        
        self.browser = await self.playwright.chromium.launch(
            headless=is_headless,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-features=VizDisplayCompositor',
                '--use-gl=swiftshader'  # WebGL 지문 생성
            ]
        )
        
        debug_status = "DEBUG" if not is_headless else "운영"
        self.logger.info(f"올리브영 쿠키 매니저 초기화 완료 ({debug_status} 모드)")
        
    async def stop(self):
        """리소스 정리."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.logger.info("올리브영 쿠키 매니저 종료 완료")
    
    async def bootstrap_cookies(self) -> bool:
        """
        Cloudflare 챌린지를 통과하여 쿠키를 발급받는다.
        
        Returns:
            쿠키 발급 성공 여부
        """
        self.logger.info("올리브영 쿠키 부트스트랩 시작")
        
        try:
            # 리소스 차단 없는 컨텍스트 생성
            context = await self.browser.new_context(
                user_agent=self.FIXED_USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"',
                    'accept-language': 'ko-KR,ko;q=0.9,en;q=0.8',
                    'accept-encoding': 'gzip, deflate, br'
                }
            )
            
            page = await context.new_page()
            
            # 메인 페이지 접속 (Cloudflare 챌린지 통과)
            self.logger.info(f"올리브영 메인 페이지 접속: {self.BOOTSTRAP_URL}")
            response = await page.goto(
                self.BOOTSTRAP_URL, 
                wait_until="domcontentloaded",
                timeout=60000
            )
            
            self.logger.info(f"페이지 응답 상태: {response.status}")
            
            # Cloudflare Turnstile 감지 및 재시도 로직
            max_turnstile_retries = 3
            for attempt in range(max_turnstile_retries):
                try:
                    # Cloudflare Turnstile iframe 감지
                    turnstile_frame = await page.wait_for_selector(
                        "iframe[src*='challenges']", 
                        timeout=30000
                    )
                    if turnstile_frame:
                        self.logger.warning(f"Cloudflare Turnstile 감지 (시도 {attempt + 1}/{max_turnstile_retries})")
                        await asyncio.sleep(15)  # Turnstile 처리 대기
                        continue
                        
                except Exception:
                    # Turnstile이 없으면 정상 진행
                    break
            
            # 기본 로드 완료 대기
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=30000)
                await asyncio.sleep(5)  # 추가 안정화 대기
            except Exception as e:
                self.logger.warning(f"페이지 로드 대기 중 오류: {e}")
            
            # 쿠키 확인
            cookies = await context.cookies()
            cookie_names = [cookie['name'] for cookie in cookies]
            
            self.logger.info(f"획득한 쿠키 목록: {cookie_names}")
            
            # 필수 쿠키 확인
            missing_cookies = [name for name in self.REQUIRED_COOKIES if name not in cookie_names]
            
            if missing_cookies:
                self.logger.warning(f"누락된 필수 쿠키: {missing_cookies}")
                
                # Cloudflare 쿠키가 없어도 세션 쿠키라도 있으면 진행
                if 'OYSESSIONID' in cookie_names:
                    self.logger.info("세션 쿠키(OYSESSIONID)가 있어 진행합니다")
                else:
                    self.logger.error("필수 세션 쿠키도 없습니다")
                    await context.close()
                    return False
            else:
                self.logger.info("모든 필수 쿠키 획득 완료")
            
            # 쿠키 상태 저장 (파일 잠금 사용)
            with FileLock(str(self.cookie_file) + ".lock"):
                await context.storage_state(path=str(self.cookie_file))
            self.logger.info(f"쿠키 상태 저장 완료: {self.cookie_file}")
            
            await context.close()
            return True
            
        except Exception as e:
            self.logger.error(f"쿠키 부트스트랩 실패: {e}")
            return False
    
    def _cookie_expired(self, state: dict) -> bool:
        """
        쿠키 만료 여부를 검사한다.
        
        Args:
            state: 저장된 브라우저 상태 딕셔너리
            
        Returns:
            만료되었으면 True, 유효하면 False
        """
        try:
            # cf_clearance 쿠키 찾기
            cookies = state.get('cookies', [])
            cf_clearance_cookie = None
            
            for cookie in cookies:
                if cookie.get('name') == 'cf_clearance':
                    cf_clearance_cookie = cookie
                    break
            
            if not cf_clearance_cookie:
                self.logger.warning("cf_clearance 쿠키를 찾을 수 없음")
                return True
            
            # 만료 시점 확인 (현재 시간 + 60초 여유)
            expires = cf_clearance_cookie.get('expires', 0)
            current_time = time.time()
            
            if expires < current_time + 60:
                self.logger.warning(f"cf_clearance 쿠키 만료: {expires} < {current_time + 60}")
                return True
            
            self.logger.debug(f"cf_clearance 쿠키 유효: {expires - current_time:.0f}초 남음")
            return False
            
        except Exception as e:
            self.logger.error(f"쿠키 만료 검사 실패: {e}")
            return True
    
    async def ensure_context(self) -> BrowserContext:
        """
        만료 검증 후 유효한 컨텍스트를 반환한다 (없으면 재부트스트랩).
        
        Returns:
            유효한 크롤링용 브라우저 컨텍스트
            
        Raises:
            Exception: 컨텍스트 생성 실패 시
        """
        needs_bootstrap = False
        
        # 쿠키 파일 존재 여부 확인
        if not self.cookie_file.exists():
            self.logger.info("쿠키 파일이 없어 부트스트랩 실행")
            needs_bootstrap = True
        else:
            # 쿠키 만료 검사
            try:
                with FileLock(str(self.cookie_file) + ".lock"):
                    with open(self.cookie_file, 'r', encoding='utf-8') as f:
                        state = json.load(f)
                    
                    if self._cookie_expired(state):
                        self.logger.info("쿠키가 만료되어 재부트스트랩 실행")
                        needs_bootstrap = True
                    else:
                        self.logger.info("쿠키가 유효함")
                        
            except Exception as e:
                self.logger.warning(f"쿠키 파일 로드 실패: {e}, 재부트스트랩 실행")
                needs_bootstrap = True
        
        # 필요시 부트스트랩 실행
        if needs_bootstrap:
            success = await self.bootstrap_cookies()
            if not success:
                raise Exception("쿠키 부트스트랩 실패")
        
        # 유효한 컨텍스트 반환
        context = await self.get_crawl_context()
        if not context:
            raise Exception("크롤링 컨텍스트 생성 실패")
            
        return context
    
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
            
            # 파일 잠금을 사용한 안전한 컨텍스트 생성
            with FileLock(str(self.cookie_file) + ".lock"):
                context = await self.browser.new_context(
                    storage_state=str(self.cookie_file),
                    user_agent=self.FIXED_USER_AGENT,
                    viewport={'width': 1920, 'height': 1080},
                    extra_http_headers={
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
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
                self.logger.debug(f"필수 API 통과: {url}")
                await route.continue_()
                return
            
            # 2. Stylesheet 무조건 차단 (속도 최적화)
            if resource_type == "stylesheet":
                await route.abort()
                return
            
            # 3. 이미지 리소스 처리 - 허용 조건 완화
            if resource_type == "image":
                if ("oliveyoung.co.kr" in url or "cloudfront" in url):
                    await route.continue_()
                    return
                else:
                    await route.abort()
                    return
            
            # 4. 폰트, 미디어 파일 차단
            if (resource_type in ["font", "media"] or 
                any(ext in url.lower() for ext in 
                    ['.woff', '.woff2', '.ttf', '.otf', '.eot', 
                     '.mp4', '.avi', '.mov', '.wmv', '.mp3', '.wav', '.ogg'])):
                await route.abort()
                return
            
            # 5. 광고 및 추적 스크립트 차단 (확장)
            blocked_domains = [
                'google-analytics.com', 'googletagmanager.com', 'facebook.com/tr',
                'doubleclick.net', 'googlesyndication.com', 'adsystem.com',
                'datadog', 'amplitude'
            ]
            
            if any(domain in url.lower() for domain in blocked_domains):
                await route.abort()
                return
            
            # 6. 그 외 요청은 정상 처리
            await route.continue_()
        
        await context.route("**/*", handle_route)
        self.logger.info("리소스 차단 설정 완료")
    
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
            self.logger.info("기존 컨텍스트 종료")
        
        self.logger.info("쿠키 리프레시 시작")
        
        # 쿠키 재발급
        if await self.bootstrap_cookies():
            # 새 컨텍스트 생성
            new_context = await self.get_crawl_context()
            if new_context:
                self.logger.info("쿠키 리프레시 및 새 컨텍스트 생성 완료")
                return new_context
        
        self.logger.error("쿠키 리프레시 실패")
        return None
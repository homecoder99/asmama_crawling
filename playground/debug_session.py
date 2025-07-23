#!/usr/bin/env python3
"""
크롤러 디버깅 세션 플레이그라운드.

단계별 크롤링 프로세스를 실행하고 각 단계에서 상태를 확인할 수 있습니다.

사용법:
    python playground/debug_session.py --branduid=1234567 --verbose
    python playground/debug_session.py --step-by-step --headless=false
"""

import sys
import argparse
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawler.base import BaseCrawler
from crawler.utils import setup_logger, random_delay
from crawler.storage import JSONStorage

logger = setup_logger(__name__)


class DebugCrawler(BaseCrawler):
    """
    디버깅 전용 크롤러.
    
    각 단계별로 상태를 확인하고 로그를 자세히 출력한다.
    """
    
    def __init__(self, headless: bool = True, verbose: bool = False):
        """
        디버그 크롤러 초기화.
        
        Args:
            headless: 헤들리스 모드 여부
            verbose: 상세 로그 출력 여부
        """
        super().__init__(storage=None, max_workers=1)
        self.headless = headless
        self.verbose = verbose
        self.step_results = {}
    
    async def start(self) -> None:
        """브라우저 시작 (디버그 정보 포함)."""
        try:
            print("🚀 브라우저 초기화 중...")
            
            from playwright.async_api import async_playwright
            
            self.playwright = await async_playwright().start()
            
            launch_options = {
                'headless': self.headless,
                'args': ['--no-sandbox', '--disable-setuid-sandbox']
            }
            
            if not self.headless:
                launch_options['slow_mo'] = 1000  # 1초 지연
            
            if self.verbose:
                print(f"  브라우저 옵션: {launch_options}")
            
            self.browser = await self.playwright.chromium.launch(**launch_options)
            
            print("✅ 브라우저 초기화 완료")
            
            if not self.headless:
                print("👁️  브라우저 창이 열렸습니다. 디버깅을 위해 헤들리스 모드가 비활성화되었습니다.")
                
        except Exception as e:
            print(f"❌ 브라우저 초기화 실패: {str(e)}")
            raise
    
    async def debug_page_load(self, url: str) -> Dict[str, Any]:
        """
        페이지 로드 디버깅.
        
        Args:
            url: 로드할 URL
            
        Returns:
            페이지 로드 결과
        """
        print(f"\n📄 페이지 로드 디버깅: {url}")
        print("-" * 50)
        
        result = {
            "url": url,
            "success": False,
            "load_time": 0,
            "final_url": None,
            "title": None,
            "errors": []
        }
        
        try:
            import time
            
            context = await self.create_context()
            page = await self.create_page(context)
            
            # 네트워크 이벤트 모니터링
            requests = []
            responses = []
            
            page.on("request", lambda req: requests.append({
                "url": req.url,
                "method": req.method,
                "headers": dict(req.headers)
            }))
            
            page.on("response", lambda resp: responses.append({
                "url": resp.url,
                "status": resp.status,
                "headers": dict(resp.headers) if hasattr(resp, 'headers') else {}
            }))
            
            # 콘솔 메시지 모니터링
            console_messages = []
            page.on("console", lambda msg: console_messages.append({
                "type": msg.type,
                "text": msg.text
            }))
            
            # 페이지 로드 시간 측정
            start_time = time.time()
            
            print("🌐 페이지 이동 중...")
            await page.goto(url, timeout=30000, wait_until='domcontentloaded')
            
            load_time = time.time() - start_time
            
            # 추가 대기 (JavaScript 실행 등)
            await random_delay(1, 2)
            
            # 페이지 정보 수집
            final_url = page.url
            title = await page.title()
            
            result.update({
                "success": True,
                "load_time": load_time,
                "final_url": final_url,
                "title": title,
                "requests_count": len(requests),
                "responses_count": len(responses),
                "console_messages": console_messages
            })
            
            print(f"✅ 페이지 로드 성공")
            print(f"  로드 시간: {load_time:.2f}초")
            print(f"  최종 URL: {final_url}")
            print(f"  페이지 제목: {title}")
            print(f"  네트워크 요청: {len(requests)}개")
            print(f"  네트워크 응답: {len(responses)}개")
            
            if console_messages:
                print(f"  콘솔 메시지: {len(console_messages)}개")
                for msg in console_messages[:3]:  # 처음 3개만
                    print(f"    [{msg['type']}] {msg['text']}")
            
            if self.verbose:
                print("\n📊 상세 네트워크 정보:")
                for i, resp in enumerate(responses[:5]):  # 처음 5개만
                    print(f"  {i+1}. {resp['status']} {resp['url']}")
            
            await context.close()
            
        except Exception as e:
            error_msg = str(e)
            result["errors"].append(error_msg)
            print(f"❌ 페이지 로드 실패: {error_msg}")
        
        self.step_results["page_load"] = result
        return result
    
    async def debug_element_extraction(self, url: str, selectors: Dict[str, str]) -> Dict[str, Any]:
        """
        엘리먼트 추출 디버깅.
        
        Args:
            url: 대상 URL
            selectors: 테스트할 셀렉터들
            
        Returns:
            엘리먼트 추출 결과
        """
        print(f"\n🔍 엘리먼트 추출 디버깅")
        print("-" * 50)
        
        result = {
            "selectors": {},
            "page_content_length": 0,
            "total_elements": 0
        }
        
        try:
            context = await self.create_context()
            page = await self.create_page(context)
            
            await self.safe_goto(page, url)
            
            # 페이지 콘텐츠 길이
            content = await page.content()
            result["page_content_length"] = len(content)
            
            # 전체 엘리먼트 수
            all_elements = await page.query_selector_all("*")
            result["total_elements"] = len(all_elements)
            
            print(f"📄 페이지 분석:")
            print(f"  HTML 길이: {len(content):,}자")
            print(f"  전체 엘리먼트: {len(all_elements)}개")
            print("")
            
            for name, selector in selectors.items():
                print(f"🎯 {name} 추출 테스트: '{selector}'")
                
                selector_result = {
                    "selector": selector,
                    "found": False,
                    "text": None,
                    "text_length": 0,
                    "attributes": {},
                    "error": None
                }
                
                try:
                    # 엘리먼트 존재 확인
                    element = await page.query_selector(selector)
                    
                    if element:
                        selector_result["found"] = True
                        
                        # 텍스트 추출
                        text = await element.inner_text()
                        selector_result["text"] = text
                        selector_result["text_length"] = len(text) if text else 0
                        
                        # 주요 속성 추출
                        for attr in ['src', 'href', 'class', 'id']:
                            attr_value = await element.get_attribute(attr)
                            if attr_value:
                                selector_result["attributes"][attr] = attr_value
                        
                        print(f"  ✅ 발견됨")
                        if text:
                            preview = text[:100] + "..." if len(text) > 100 else text
                            print(f"     텍스트: {preview}")
                        
                        if selector_result["attributes"]:
                            print(f"     속성: {selector_result['attributes']}")
                    else:
                        print(f"  ❌ 엘리먼트를 찾을 수 없음")
                
                except Exception as e:
                    selector_result["error"] = str(e)
                    print(f"  💥 오류: {str(e)}")
                
                result["selectors"][name] = selector_result
                print("")
            
            await context.close()
            
        except Exception as e:
            print(f"❌ 엘리먼트 추출 디버깅 실패: {str(e)}")
        
        self.step_results["element_extraction"] = result
        return result
    
    async def debug_full_crawl(self, branduid: str) -> Dict[str, Any]:
        """
        전체 크롤링 프로세스 디버깅.
        
        Args:
            branduid: 크롤링할 제품 ID
            
        Returns:
            크롤링 결과
        """
        print(f"\n🕷️  전체 크롤링 디버깅: branduid={branduid}")
        print("-" * 50)
        
        url = f"http://www.asmama.com/shop/shopdetail.html?branduid={branduid}"
        
        # 1단계: 페이지 로드
        load_result = await self.debug_page_load(url)
        
        if not load_result["success"]:
            return {"error": "페이지 로드 실패", "results": self.step_results}
        
        # 2단계: 엘리먼트 추출
        selectors = {
            "제품명": "h1, .product-title, .item-name, .product-name, title",
            "가격": ".price, .product-price, .item-price, .cost",
            "이미지": "img",
            "옵션": ".options, .product-options, select",
            "설명": ".description, .product-description, .detail"
        }
        
        extraction_result = await self.debug_element_extraction(url, selectors)
        
        # 3단계: 데이터 구조화
        print(f"\n📦 데이터 구조화")
        print("-" * 30)
        
        product_data = {
            "branduid": branduid,
            "name": None,
            "price": None,
            "options": [],
            "image_urls": [],
            "detail_html": ""
        }
        
        # 추출된 데이터에서 실제 값 설정
        for field, selector_result in extraction_result["selectors"].items():
            if selector_result["found"] and selector_result["text"]:
                if field == "제품명":
                    product_data["name"] = selector_result["text"]
                elif field == "가격":
                    from crawler.utils import parse_price
                    product_data["price"] = parse_price(selector_result["text"])
        
        print(f"✅ 구조화된 데이터:")
        for key, value in product_data.items():
            if value:
                preview = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                print(f"  {key}: {preview}")
        
        final_result = {
            "product_data": product_data,
            "debug_steps": self.step_results
        }
        
        return final_result


async def run_debug_session(args):
    """디버그 세션 실행."""
    crawler = DebugCrawler(headless=args.headless, verbose=args.verbose)
    
    try:
        async with crawler:
            if args.step_by_step:
                print("⏯️  단계별 실행 모드")
                input("Enter를 눌러 시작...")
            
            if args.branduid:
                result = await crawler.debug_full_crawl(args.branduid)
                
                # 결과 저장
                if args.save_results:
                    results_dir = Path("playground/results")
                    results_dir.mkdir(parents=True, exist_ok=True)
                    
                    storage = JSONStorage(f"playground/results/debug_{args.branduid}.json")
                    storage.save(result)
                    print(f"\n💾 디버그 결과 저장: debug_{args.branduid}.json")
                
            elif args.url:
                await crawler.debug_page_load(args.url)
            
    except KeyboardInterrupt:
        print("\n🛑 사용자에 의해 중단됨")
    except Exception as e:
        print(f"\n💥 디버그 세션 오류: {str(e)}")
        logger.error(f"디버그 세션 실패: {str(e)}", exc_info=True)


def main():
    """메인 함수."""
    parser = argparse.ArgumentParser(description="크롤러 디버깅 세션")
    parser.add_argument(
        "--branduid",
        type=str,
        help="디버깅할 제품의 branduid"
    )
    parser.add_argument(
        "--url",
        type=str,
        help="디버깅할 커스텀 URL"
    )
    parser.add_argument(
        "--headless",
        type=bool,
        default=True,
        help="헤들리스 모드 (기본: True)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="상세 로그 출력"
    )
    parser.add_argument(
        "--step-by-step",
        action="store_true",
        help="단계별 실행 (수동 진행)"
    )
    parser.add_argument(
        "--save-results",
        action="store_true",
        help="디버그 결과 저장"
    )
    
    args = parser.parse_args()
    
    print("🐛 크롤러 디버깅 플레이그라운드")
    print("=" * 40)
    
    if not args.branduid and not args.url:
        print("❌ --branduid 또는 --url 인자가 필요합니다.")
        print("💡 예시:")
        print("  python playground/debug_session.py --branduid=1234567 --verbose")
        print("  python playground/debug_session.py --url='http://example.com' --headless=false")
        sys.exit(1)
    
    if args.step_by_step and args.headless:
        print("💡 단계별 실행을 위해 헤들리스 모드를 비활성화합니다.")
        args.headless = False
    
    # 디버그 세션 실행
    asyncio.run(run_debug_session(args))


if __name__ == "__main__":
    main()
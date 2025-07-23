#!/usr/bin/env python3
"""
CSS 셀렉터 실험 및 검증 플레이그라운드.

실제 Asmama 사이트에서 셀렉터를 테스트하고 데이터 추출을 검증합니다.

사용법:
    python playground/test_selectors.py --branduid=1234567
    python playground/test_selectors.py --url="http://example.com" --test-mode
"""

import sys
import argparse
import asyncio
from pathlib import Path
from typing import Dict, List, Optional

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawler.base import BaseCrawler
from crawler.utils import setup_logger, clean_text, parse_price

logger = setup_logger(__name__)


class SelectorTester(BaseCrawler):
    """
    셀렉터 테스트 전용 크롤러.
    
    다양한 CSS 셀렉터를 시도하고 결과를 비교분석한다.
    """
    
    def __init__(self):
        """셀렉터 테스터 초기화."""
        super().__init__(storage=None, max_workers=1)
    
    async def test_selectors(self, url: str, selector_groups: Dict[str, List[str]]) -> Dict[str, any]:
        """
        여러 셀렉터 그룹을 테스트한다.
        
        Args:
            url: 테스트할 페이지 URL
            selector_groups: 테스트할 셀렉터 그룹들
            
        Returns:
            셀렉터별 테스트 결과
        """
        async with self:
            page = await self.create_page()
            
            if not await self.safe_goto(page, url):
                return {"error": "페이지 로드 실패"}
            
            results = {}
            
            for group_name, selectors in selector_groups.items():
                print(f"\n🔍 {group_name} 셀렉터 테스트:")
                group_results = []
                
                for selector in selectors:
                    try:
                        # 텍스트 추출 시도
                        text = await self.safe_get_text(page, selector)
                        
                        # 요소 존재 여부 확인
                        element_exists = await self.safe_wait_for_selector(page, selector, timeout=1000)
                        
                        # 속성 추출 시도 (이미지 등)
                        src_attr = await self.safe_get_attribute(page, selector, 'src')
                        href_attr = await self.safe_get_attribute(page, selector, 'href')
                        
                        result = {
                            "selector": selector,
                            "exists": element_exists,
                            "text": clean_text(text) if text else None,
                            "src": src_attr,
                            "href": href_attr,
                            "text_length": len(text) if text else 0
                        }
                        
                        group_results.append(result)
                        
                        # 결과 출력
                        status = "✅" if element_exists else "❌"
                        print(f"  {status} {selector}")
                        if text:
                            preview = text[:50] + "..." if len(text) > 50 else text
                            print(f"     📝 텍스트: {preview}")
                        if src_attr:
                            print(f"     🖼️  src: {src_attr}")
                        if href_attr:
                            print(f"     🔗 href: {href_attr}")
                            
                    except Exception as e:
                        result = {
                            "selector": selector,
                            "error": str(e)
                        }
                        group_results.append(result)
                        print(f"  ❌ {selector} - 오류: {str(e)}")
                
                results[group_name] = group_results
            
            await page.close()
            return results
    
    async def analyze_page_structure(self, url: str) -> Dict[str, any]:
        """
        페이지 구조를 분석한다.
        
        Args:
            url: 분석할 페이지 URL
            
        Returns:
            페이지 구조 분석 결과
        """
        async with self:
            page = await self.create_page()
            
            if not await self.safe_goto(page, url):
                return {"error": "페이지 로드 실패"}
            
            print("🔍 페이지 구조 분석 중...")
            
            # 기본 정보
            title = await page.title()
            url_final = page.url
            
            # 주요 태그 분석
            tag_counts = {}
            important_tags = ['h1', 'h2', 'h3', 'img', 'a', 'div', 'span', 'p', 'table', 'form']
            
            for tag in important_tags:
                elements = await page.query_selector_all(tag)
                tag_counts[tag] = len(elements)
            
            # 클래스와 ID 분석
            class_elements = await page.query_selector_all('[class]')
            id_elements = await page.query_selector_all('[id]')
            
            # 폼 요소 분석
            forms = await page.query_selector_all('form')
            inputs = await page.query_selector_all('input')
            
            # 이미지 분석
            images = await page.query_selector_all('img')
            image_info = []
            for img in images[:5]:  # 처음 5개만
                src = await img.get_attribute('src')
                alt = await img.get_attribute('alt')
                if src:
                    image_info.append({"src": src, "alt": alt})
            
            result = {
                "title": title,
                "url": url_final,
                "tag_counts": tag_counts,
                "elements_with_class": len(class_elements),
                "elements_with_id": len(id_elements),
                "forms": len(forms),
                "inputs": len(inputs),
                "images_sample": image_info
            }
            
            # 결과 출력
            print(f"📄 제목: {title}")
            print(f"🌐 URL: {url_final}")
            print(f"🏷️  클래스가 있는 요소: {len(class_elements)}개")
            print(f"🆔 ID가 있는 요소: {len(id_elements)}개")
            print("📊 태그 통계:")
            for tag, count in tag_counts.items():
                if count > 0:
                    print(f"  {tag}: {count}개")
            
            await page.close()
            return result


async def test_asmama_selectors(branduid: str):
    """
    Asmama 사이트 전용 셀렉터 테스트.
    
    Args:
        branduid: 테스트할 제품의 branduid
    """
    url = f"http://www.asmama.com/shop/shopdetail.html?branduid={branduid}"
    
    print(f"🎯 Asmama 셀렉터 테스트: {url}")
    print("=" * 60)
    
    tester = SelectorTester()
    
    # 테스트할 셀렉터 그룹들
    selector_groups = {
        "제품명": [
            "h1",
            ".product-title",
            ".item-name",
            ".product-name",
            "title",
            ".title",
            "#product-title",
            ".product_title"
        ],
        "가격": [
            ".price",
            ".product-price",
            ".item-price",
            ".cost",
            ".product_price",
            "#price",
            "[class*='price']",
            ".sale-price"
        ],
        "이미지": [
            "img",
            ".product-image img",
            ".item-image img",
            "#product-image img",
            ".thumbnail img",
            ".main-image img"
        ],
        "옵션": [
            ".options",
            ".product-options",
            ".item-options",
            "select",
            ".option-select",
            ".variant-select"
        ],
        "설명": [
            ".description",
            ".product-description",
            ".detail",
            ".product-detail",
            ".content",
            "#description"
        ]
    }
    
    # 셀렉터 테스트 실행
    results = await tester.test_selectors(url, selector_groups)
    
    # 페이지 구조 분석
    print("\n🏗️  페이지 구조 분석:")
    print("=" * 30)
    structure = await tester.analyze_page_structure(url)
    
    return results, structure


async def test_custom_url(url: str):
    """
    사용자 지정 URL 테스트.
    
    Args:
        url: 테스트할 URL
    """
    print(f"🌐 커스텀 URL 테스트: {url}")
    print("=" * 60)
    
    tester = SelectorTester()
    
    # 기본 셀렉터들
    basic_selectors = {
        "제목": ["h1", "h2", "title", ".title"],
        "텍스트": ["p", ".content", ".description"],
        "링크": ["a[href]"],
        "이미지": ["img[src]"],
        "리스트": ["ul li", "ol li"]
    }
    
    results = await tester.test_selectors(url, basic_selectors)
    structure = await tester.analyze_page_structure(url)
    
    return results, structure


def save_results(results: Dict, structure: Dict, output_file: str = "playground/results/selector_test.json"):
    """
    테스트 결과를 저장한다.
    
    Args:
        results: 셀렉터 테스트 결과
        structure: 페이지 구조 분석 결과
        output_file: 저장할 파일 경로
    """
    import json
    from datetime import datetime
    
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        "timestamp": datetime.now().isoformat(),
        "selector_results": results,
        "page_structure": structure
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"💾 결과 저장 완료: {output_path}")


def main():
    """메인 함수."""
    parser = argparse.ArgumentParser(description="CSS 셀렉터 테스트 도구")
    parser.add_argument(
        "--branduid",
        type=str,
        help="Asmama 제품의 branduid"
    )
    parser.add_argument(
        "--url",
        type=str,
        help="테스트할 커스텀 URL"
    )
    parser.add_argument(
        "--output",
        default="playground/results/selector_test.json",
        help="결과 저장 파일"
    )
    
    args = parser.parse_args()
    
    print("🧪 셀렉터 테스트 플레이그라운드")
    print("=" * 40)
    
    if args.branduid:
        results, structure = asyncio.run(test_asmama_selectors(args.branduid))
    elif args.url:
        results, structure = asyncio.run(test_custom_url(args.url))
    else:
        print("❌ --branduid 또는 --url 인자가 필요합니다.")
        print("💡 예시:")
        print("  python playground/test_selectors.py --branduid=1234567")
        print("  python playground/test_selectors.py --url='http://example.com'")
        sys.exit(1)
    
    # 결과 저장
    save_results(results, structure, args.output)


if __name__ == "__main__":
    main()
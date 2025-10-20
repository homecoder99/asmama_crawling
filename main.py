"""Asmama 크롤러의 메인 진입점."""

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from crawler.asmama import AsmamaCrawler
from crawler.oliveyoung import OliveyoungCrawler
from crawler.storage import ExcelStorage
from crawler.utils import setup_logger

logger = setup_logger(__name__)


def main():
    """
    크롤러의 메인 함수.
    
    명령행 인자를 파싱하고 크롤러를 실행한다.
    Asmama 또는 Oliveyoung 사이트를 선택하여 크롤링할 수 있다.
    
    Oliveyoung 크롤링 옵션:
    1. 단일 제품: --goods-no A000000192405
    2. 특정 카테고리: --category-id 100000100010001 --max-items-per-category 20
    3. 모든 카테고리: --all-categories --max-items-per-category 15
    4. 기존 URL 방식: --list-url "https://www.oliveyoung.co.kr/store/display/getMCategoryList.do?dispCatNo=..."
    """
    parser = argparse.ArgumentParser(description="웹 제품 크롤러 (Asmama / Oliveyoung)")
    
    # 사이트 선택
    parser.add_argument(
        "--site",
        type=str,
        choices=["asmama", "oliveyoung"],
        help="크롤링할 사이트 선택 (asmama 또는 oliveyoung)",
        default="asmama"
    )
    
    # Asmama용 파라미터
    parser.add_argument(
        "--branduid",
        type=str,
        help="Asmama 제품의 branduid (단일 제품 크롤링 시)",
        default=None
    )
    
    # Oliveyoung용 파라미터
    parser.add_argument(
        "--goods-no",
        type=str,
        help="Oliveyoung 제품의 goodsNo (단일 제품 크롤링 시)",
        default=None
    )
    
    # 공통 파라미터
    parser.add_argument(
        "--list-url",
        type=str,
        help="제품 목록 페이지 URL (리스트 크롤링 시)",
        default=None
    )
    parser.add_argument(
        "--max-items",
        type=int,
        help="최대 크롤링 아이템 수 (리스트 크롤링 시)",
        default=30
    )
    parser.add_argument(
        "--category-id",
        type=str,
        help="Oliveyoung 특정 카테고리 ID (단일 카테고리 크롤링 시)",
        default=None
    )
    parser.add_argument(
        "--all-categories",
        action="store_true",
        help="Oliveyoung 모든 카테고리 크롤링",
        default=False
    )
    parser.add_argument(
        "--max-items-per-category",
        type=int,
        help="카테고리당 최대 크롤링 아이템 수 (카테고리 크롤링 시)",
        default=15
    )
    parser.add_argument(
        "--new-products-only",
        action="store_true",
        help="Oliveyoung 최신 상품만 크롤링 (기존 엑셀 파일과 비교)",
        default=False
    )
    parser.add_argument(
        "--existing-excel",
        type=str,
        help="기존 크롤링 결과 엑셀 파일 경로 (--new-products-only와 함께 사용)",
        default=None
    )
    parser.add_argument(
        "--output",
        help="출력 Excel 파일 경로",
        default=None
    )
    
    args = parser.parse_args()
    
    # 입력 검증
    if args.site == "asmama":
        if not args.branduid and not args.list_url:
            parser.error("Asmama: --branduid 또는 --list-url 중 하나는 필수입니다.")
        if args.branduid and args.list_url:
            parser.error("Asmama: --branduid와 --list-url은 동시에 사용할 수 없습니다.")
    elif args.site == "oliveyoung":
        # Oliveyoung 옵션 검증
        options_count = sum([
            bool(args.goods_no),
            bool(args.list_url),
            bool(args.category_id),
            args.all_categories,
            args.new_products_only
        ])

        if options_count == 0:
            parser.error("Oliveyoung: --goods-no, --list-url, --category-id, --all-categories, 또는 --new-products-only 중 하나는 필수입니다.")
        if options_count > 1:
            parser.error("Oliveyoung: 여러 옵션을 동시에 사용할 수 없습니다.")

        # --new-products-only 사용 시 --existing-excel 필수
        if args.new_products_only and not args.existing_excel:
            parser.error("Oliveyoung: --new-products-only 옵션 사용 시 --existing-excel은 필수입니다.")
    
    # 기본 출력 파일 경로 설정
    if args.output is None:
        if args.site == "asmama":
            args.output = "data/asmama_products.xlsx"
        else:  # oliveyoung
            args.output = "data/oliveyoung_products.xlsx"
    
    try:
        logger.info(f"{args.site.capitalize()} 크롤러 시작...")
        
        # 출력 디렉토리 생성
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 사이트별 크롤러 초기화
        storage = ExcelStorage(str(output_path))
        
        if args.site == "asmama":
            crawler = AsmamaCrawler(storage=storage)
            
            # Asmama 크롤러 실행
            if args.branduid:
                logger.info(f"Asmama 단일 제품 크롤링: branduid={args.branduid}")
                
                async def run_asmama_single():
                    async with crawler:
                        return await crawler.crawl_single_product(args.branduid)
                
                import asyncio
                product = asyncio.run(run_asmama_single())
                products = [product] if product else []
            else:
                logger.info(f"Asmama 리스트 페이지 크롤링: {args.list_url}")
                
                async def run_asmama_list():
                    async with crawler:
                        # branduid 목록 추출
                        branduid_list = await crawler._extract_branduid_list(args.list_url, args.max_items)
                        if branduid_list:
                            return await crawler.crawl_from_branduid_list(branduid_list)
                        return []
                
                import asyncio
                products = asyncio.run(run_asmama_list())
                
        else:  # oliveyoung
            crawler = OliveyoungCrawler(storage=storage)
            
            # Oliveyoung 크롤러 실행
            if args.goods_no:
                logger.info(f"Oliveyoung 단일 제품 크롤링: goodsNo={args.goods_no}")
                
                async def run_oliveyoung_single():
                    async with crawler:
                        return await crawler.crawl_single_product(args.goods_no)
                
                import asyncio
                product = asyncio.run(run_oliveyoung_single())
                products = [product] if product else []
                
            elif args.category_id:
                logger.info(f"Oliveyoung 특정 카테고리 크롤링: categoryId={args.category_id}")
                
                async def run_oliveyoung_single_category():
                    async with crawler:
                        return await crawler.crawl_from_category(args.category_id, args.max_items_per_category)
                
                import asyncio
                products = asyncio.run(run_oliveyoung_single_category())
                
            elif args.all_categories:
                logger.info(f"Oliveyoung 모든 카테고리 크롤링 (카테고리당 최대 {args.max_items_per_category}개)")

                async def run_oliveyoung_all_categories():
                    async with crawler:
                        return await crawler.crawl_all_categories(args.max_items_per_category)

                import asyncio
                products = asyncio.run(run_oliveyoung_all_categories())

            elif args.new_products_only:
                logger.info(f"Oliveyoung 최신 상품만 크롤링 (기존: {args.existing_excel})")

                async def run_oliveyoung_new_products():
                    async with crawler:
                        return await crawler.crawl_new_products_only(
                            existing_excel_path=args.existing_excel,
                            max_items_per_category=args.max_items_per_category
                        )

                import asyncio
                products = asyncio.run(run_oliveyoung_new_products())

            else:  # list-url 옵션
                logger.info(f"Oliveyoung 카테고리 페이지 크롤링: {args.list_url}")
                
                async def run_oliveyoung_legacy_category():
                    async with crawler:
                        # 기존 방식과 호환성을 위해 URL에서 categoryId 추출 시도
                        try:
                            from urllib.parse import urlparse, parse_qs
                            parsed_url = urlparse(args.list_url)
                            query_params = parse_qs(parsed_url.query)
                            category_id = query_params.get('dispCatNo', [None])[0]
                            
                            if category_id:
                                return await crawler.crawl_from_category(category_id, args.max_items)
                            else:
                                logger.error("URL에서 dispCatNo 파라미터를 찾을 수 없습니다.")
                                return []
                        except Exception as e:
                            logger.error(f"URL 파싱 실패: {str(e)}")
                            return []
                
                import asyncio
                products = asyncio.run(run_oliveyoung_legacy_category())
        
        # 결과 요약 출력
        if products:
            logger.info(f"총 {len(products)}개 제품 크롤링 완료")
            logger.info(f"결과 저장 위치: {output_path}")
            
            # 카테고리별 통계 (Oliveyoung인 경우)
            if args.site == "oliveyoung" and args.all_categories:
                category_stats = {}
                for product in products:
                    category = product.get('category_name', '미분류')
                    category_stats[category] = category_stats.get(category, 0) + 1
                
                logger.info("카테고리별 크롤링 결과:")
                for category, count in category_stats.items():
                    logger.info(f"  - {category}: {count}개")
        else:
            logger.warning("크롤링된 제품이 없습니다.")
        
    except Exception as e:
        logger.error(f"크롤러 실행 실패: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
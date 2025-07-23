"""Asmama 크롤러의 메인 진입점."""

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from crawler.asmama import AsmamaCrawler
from crawler.storage import ExcelStorage
from crawler.utils import setup_logger

logger = setup_logger(__name__)


def main():
    """
    Asmama 크롤러의 메인 함수.
    
    명령행 인자를 파싱하고 크롤러를 실행한다.
    단일 branduid를 받아 해당 제품을 크롤링하거나,
    리스트 페이지에서 여러 제품을 크롤링할 수 있다.
    """
    parser = argparse.ArgumentParser(description="Asmama 제품 크롤러")
    parser.add_argument(
        "--branduid",
        type=str,
        help="크롤링할 제품의 branduid (단일 제품 크롤링 시)",
        default=None
    )
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
        "--output",
        help="출력 Excel 파일 경로",
        default="data/asmama_products.xlsx"
    )
    
    args = parser.parse_args()
    
    # 입력 검증
    if not args.branduid and not args.list_url:
        parser.error("--branduid 또는 --list-url 중 하나는 필수입니다.")
    
    if args.branduid and args.list_url:
        parser.error("--branduid와 --list-url은 동시에 사용할 수 없습니다.")
    
    try:
        logger.info("Asmama 크롤러 시작...")
        
        # 출력 디렉토리 생성
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 컴포넌트 초기화
        storage = ExcelStorage(str(output_path))
        crawler = AsmamaCrawler(storage=storage)
        
        # 크롤러 실행
        if args.branduid:
            logger.info(f"단일 제품 크롤링: branduid={args.branduid}")
            product = crawler.crawl_single_product(args.branduid)
            products = [product] if product else []
        else:
            logger.info(f"리스트 페이지 크롤링: {args.list_url}")
            products = crawler.crawl_from_list(
                list_url=args.list_url,
                max_items=args.max_items
            )
        
        logger.info(f"총 {len(products)}개 제품 크롤링 완료")
        logger.info(f"결과 저장 위치: {output_path}")
        
    except Exception as e:
        logger.error(f"크롤러 실행 실패: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
"""Oliveyoung 크롤러 테스트 스크립트."""

import sys
import asyncio
import argparse
from pathlib import Path

# 상위 디렉토리의 모듈 임포트를 위한 경로 설정
sys.path.append(str(Path(__file__).parent.parent))

from crawler.oliveyoung import OliveyoungCrawler
from crawler.storage import JSONStorage, ExcelStorage
from crawler.utils import setup_logger

logger = setup_logger(__name__)


def read_category_filter_from_file(file_path: str) -> list:
    """
    파일에서 카테고리 필터링 단어를 읽어온다.
    
    Args:
        file_path: 필터링 단어가 저장된 파일 경로
        
    Returns:
        필터링 단어 목록 (줄바꿈으로 구분된 단어들)
    """
    try:
        file_path = Path(file_path)
        if not file_path.exists():
            logger.warning(f"카테고리 필터 파일이 존재하지 않음: {file_path}")
            return []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 빈 줄과 주석(#으로 시작)을 제외하고 단어 추출
        filter_words = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                filter_words.append(line)
        
        logger.info(f"카테고리 필터 파일에서 {len(filter_words)}개 단어 로드: {file_path}")
        logger.info(f"필터링 단어: {', '.join(filter_words)}")
        
        return filter_words
        
    except Exception as e:
        logger.error(f"카테고리 필터 파일 읽기 실패: {str(e)}")
        return []


def create_storage(base_name: str, use_excel: bool = False, output_filename: str = None):
    """
    저장소를 생성한다.
    
    Args:
        base_name: 기본 파일명
        use_excel: Excel 저장소 사용 여부 (기본값: False, JSON 사용)
        output_filename: 고정 출력 파일명 (지정시 타임스탬프 사용 안함)
        
    Returns:
        생성된 저장소 인스턴스
    """
    if output_filename:
        # 고정 파일명 사용
        storage_path = f"data/{output_filename}"
    else:
        # 기존 동적 파일명 사용
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if use_excel:
            storage_path = f"data/{base_name}_{timestamp}.xlsx"
        else:
            storage_path = f"data/{base_name}_{timestamp}.json"
    
    if use_excel or (output_filename and output_filename.endswith('.xlsx')):
        return ExcelStorage(storage_path)
    else:
        return JSONStorage(storage_path)


async def test_single_product(goods_no: str, use_excel: bool = False, output_filename: str = None):
    """
    단일 제품 크롤링 테스트.
    
    Args:
        goods_no: 테스트할 goodsNo
        use_excel: Excel 저장소 사용 여부
        output_filename: 고정 출력 파일명
    """
    logger.info(f"Oliveyoung 단일 제품 테스트 시작: {goods_no}")
    storage_type = "Excel" if use_excel else "JSON"
    logger.info(f"저장소 타입: {storage_type}")
    
    # 저장소 생성
    storage = create_storage(f"test_oliveyoung_{goods_no}", use_excel, output_filename)
    
    async with OliveyoungCrawler(storage=storage) as crawler:
        try:
            # 제품 크롤링
            product_data = await crawler.crawl_single_product(goods_no)
            
            if product_data:
                logger.info("제품 크롤링 성공!")
                logger.info(f"제품명: {product_data.get('item_name', 'N/A')}")
                logger.info(f"브랜드: {product_data.get('brand_name', 'N/A')}")
                logger.info(f"가격: {product_data.get('price', 'N/A')}")
                logger.info(f"카테고리: {product_data.get('category_name', 'N/A')}")
                logger.info(f"옵션 가능: {product_data.get('is_option_available', False)}")
                logger.info(f"품절 여부: {product_data.get('is_soldout', False)}")
                
                # 이미지 개수 출력
                images = product_data.get('images', '')
                image_count = len(images.split('$$')) if images else 0
                logger.info(f"이미지 개수: {image_count}")
                
                # 결과 저장
                storage.save(product_data)
                logger.info(f"결과 저장 완료: {storage.file_path}")
                
            else:
                logger.error("제품 크롤링 실패")
                
        except Exception as e:
            logger.error(f"테스트 실행 중 오류: {str(e)}", exc_info=True)


async def test_category_crawling(category_id: str, max_items: int = 10, use_excel: bool = False):
    """
    카테고리 페이지 크롤링 테스트.
    
    Args:
        category_id: 테스트할 카테고리 ID
        max_items: 최대 크롤링 아이템 수
        use_excel: Excel 저장소 사용 여부
    """
    logger.info(f"Oliveyoung 카테고리 테스트 시작: {category_id}")
    logger.info(f"최대 아이템 수: {max_items}")
    storage_type = "Excel" if use_excel else "JSON"
    logger.info(f"저장소 타입: {storage_type}")
    
    # 저장소 생성
    storage = create_storage(f"test_oliveyoung_category_{category_id}", use_excel)
    
    async with OliveyoungCrawler(storage=storage) as crawler:
        try:
            # 카테고리 크롤링
            products = await crawler.crawl_from_category(category_id, max_items)
            
            logger.info(f"총 {len(products)}개 제품 크롤링 완료")
            
            for i, product in enumerate(products[:3], 1):  # 처음 3개만 출력
                logger.info(f"제품 {i}: {product.get('item_name', 'N/A')} - {product.get('price', 'N/A')}")
            
            if products:
                # 결과 저장
                storage.save(products)
                logger.info(f"결과 저장 완료: {storage.file_path}")
            else:
                logger.warning("크롤링된 제품이 없습니다")
                
        except Exception as e:
            logger.error(f"카테고리 테스트 실행 중 오류: {str(e)}", exc_info=True)


async def test_goods_no_extraction(category_id: str, max_items: int = 10):
    """
    카테고리에서 goodsNo 추출 테스트.
    
    Args:
        category_id: 테스트할 카테고리 ID
        max_items: 최대 추출 아이템 수
    """
    logger.info(f"Oliveyoung goodsNo 추출 테스트: {category_id}")
    
    async with OliveyoungCrawler() as crawler:
        try:
            # goodsNo 목록 추출
            goods_no_list = await crawler._extract_goods_no_list_from_category(category_id, max_items)
            
            logger.info(f"추출된 goodsNo 개수: {len(goods_no_list)}")
            
            for i, goods_no in enumerate(goods_no_list[:5], 1):  # 처음 5개만 출력
                logger.info(f"goodsNo {i}: {goods_no}")
                
        except Exception as e:
            logger.error(f"goodsNo 추출 테스트 실행 중 오류: {str(e)}", exc_info=True)


async def test_category_extraction():
    """
    메인 페이지에서 카테고리 ID와 이름 추출 테스트.
    """
    logger.info("Oliveyoung 카테고리 ID와 이름 추출 테스트 시작")
    
    async with OliveyoungCrawler() as crawler:
        try:
            # 카테고리 ID와 이름 추출
            categories = await crawler.extract_all_category_ids()
            
            logger.info(f"추출된 카테고리 개수: {len(categories)}")
            
            # 길이별 카테고리 분류 및 출력
            by_length = {}
            for category in categories:
                cat_id = category["id"]
                length = len(cat_id)
                if length not in by_length:
                    by_length[length] = []
                by_length[length].append(f"{cat_id}({category['name']})")
            
            logger.info("카테고리 구조:")
            for length in sorted(by_length.keys()):
                count = len(by_length[length])
                examples = ', '.join(by_length[length][:3])
                if count > 3:
                    examples += '...'
                logger.info(f"  길이 {length:2d}자리: {count:3d}개 - {examples}")
                
        except Exception as e:
            logger.error(f"카테고리 추출 테스트 실행 중 오류: {str(e)}", exc_info=True)


async def test_category_filtering(filter_file: str = None, filter_words: list = None, max_items_per_category: int = 5, use_excel: bool = False, output_filename: str = None):
    """
    카테고리 필터링 기능 테스트.
    
    Args:
        filter_file: 필터링 단어가 저장된 파일 경로
        filter_words: 직접 전달할 필터링 단어 목록
        max_items_per_category: 카테고리당 최대 크롤링 개수
        use_excel: Excel 저장소 사용 여부
    """
    logger.info("=== Oliveyoung 카테고리 필터링 테스트 시작 ===")
    
    # 필터링 단어 준비
    if filter_file:
        category_filter = read_category_filter_from_file(filter_file)
        if not category_filter:
            logger.error("필터링 단어를 로드할 수 없습니다")
            return
    elif filter_words:
        category_filter = filter_words
        logger.info(f"직접 전달된 필터링 단어: {', '.join(category_filter)}")
    else:
        logger.error("필터링 단어가 없습니다. --filter-file 또는 --filter-words를 사용하세요.")
        return
    
    if not category_filter:
        logger.error("유효한 필터링 단어가 없습니다.")
        return
    
    logger.info(f"카테고리당 최대 아이템: {max_items_per_category}")
    storage_type = "Excel" if use_excel else "JSON"
    logger.info(f"저장소 타입: {storage_type}")
    
    # 저장소 생성
    storage = create_storage(f"oliveyoung_products", use_excel, output_filename)
    
    async with OliveyoungCrawler(storage=storage) as crawler:
        try:
            # 1단계: 모든 카테고리 추출
            logger.info("1단계: 카테고리 ID와 이름 추출 중...")
            all_categories = await crawler.extract_all_category_ids()
            
            if not all_categories:
                logger.error("카테고리를 추출할 수 없습니다")
                return
            
            logger.info(f"전체 카테고리 개수: {len(all_categories)}")
            
            # 2단계: 카테고리 필터링 테스트
            logger.info("2단계: 카테고리 필터링 적용 중...")
            
            # 수동 필터링 (테스트 확인용)
            manual_filtered = []
            filter_lower = [name.lower() for name in category_filter]
            
            for category in all_categories:
                # 현재 카테고리가 필터 목록에 있으면 건너뛴다
                if category["name"].strip().lower() in filter_lower:
                    continue
                manual_filtered.append(category)
            
            logger.info(f"수동 필터링 결과: {len(manual_filtered)}개 카테고리")
            for category in manual_filtered[:10]:  # 처음 10개만 로깅
                logger.info(f"  - {category['id']}: {category['name']}")
            if len(manual_filtered) > 10:
                logger.info(f"  ... 및 {len(manual_filtered) - 10}개 더")
            
            # 3단계: crawl_all_categories로 필터링 크롤링 실행
            logger.info("3단계: 필터링된 카테고리에서 제품 크롤링 중...")
            
            if not manual_filtered:
                logger.warning("필터링된 카테고리가 없습니다")
                return
            
            # crawl_all_categories 메서드 사용 (필터링된 모든 카테고리)
            all_products = await crawler.crawl_all_categories(
                max_items_per_category=max_items_per_category,
                category_filter=category_filter
            )
            
            # 4단계: 결과 정리
            logger.info("=== Oliveyoung 카테고리 필터링 테스트 완료 ===")
            logger.info(f"사용된 필터링 단어: {', '.join(category_filter)}")
            logger.info(f"필터링된 카테고리 개수: {len(manual_filtered)}개")
            logger.info(f"총 크롤링된 제품: {len(all_products)}개")
            
            if all_products:
                # 크롤링된 제품 정보 출력 (처음 3개만)
                logger.info("크롤링된 제품 예시:")
                for i, product in enumerate(all_products[:3], 1):
                    logger.info(f"  제품 {i}: {product.get('item_name', 'N/A')} - {product.get('price', 'N/A')} - 카테고리: {product.get('category_name', 'N/A')}")
                
                # 결과 저장
                storage.save(all_products)
                logger.info(f"결과 저장 완료: {storage.file_path}")
            else:
                logger.warning("크롤링된 제품이 없습니다")
                
        except Exception as e:
            logger.error(f"카테고리 필터링 테스트 실행 중 오류: {str(e)}", exc_info=True)


async def test_new_products_only(existing_excel: str, max_items_per_category: int = 15, use_excel: bool = True, output_filename: str = None, filter_file: str = "category_filter.txt"):
    """
    최신 상품만 크롤링 테스트 (기존 엑셀과 비교).

    Args:
        existing_excel: 기존 크롤링 결과 엑셀 파일 경로
        max_items_per_category: 카테고리당 최대 크롤링 개수
        use_excel: Excel 저장소 사용 여부
        output_filename: 출력 파일명
        filter_file: 카테고리 필터 파일 경로
    """
    logger.info("=== Oliveyoung 최신 상품 크롤링 테스트 시작 ===")
    logger.info(f"기존 데이터: {existing_excel}")
    logger.info(f"카테고리당 최대 아이템: {max_items_per_category}")

    # 기존 파일 존재 확인
    if not Path(existing_excel).exists():
        logger.error(f"기존 엑셀 파일을 찾을 수 없습니다: {existing_excel}")
        return

    # 카테고리 필터 로드
    category_filter = read_category_filter_from_file(filter_file)
    if category_filter:
        logger.info(f"카테고리 필터 적용: {len(category_filter)}개 카테고리 제외")
    else:
        logger.info("카테고리 필터 없음: 모든 카테고리 크롤링")

    # 저장소 생성
    storage = create_storage("oliveyoung_new_products", use_excel, output_filename)

    async with OliveyoungCrawler(storage=storage) as crawler:
        try:
            # 최신 상품만 크롤링
            new_products = await crawler.crawl_new_products_only(
                existing_excel_path=existing_excel,
                max_items_per_category=max_items_per_category,
                category_filter=category_filter  # 필터 적용
            )

            # 결과 정리
            logger.info("=== Oliveyoung 최신 상품 크롤링 완료 ===")
            logger.info(f"총 신규 제품: {len(new_products)}개")

            if new_products:
                # 카테고리별 통계
                category_stats = {}
                for product in new_products:
                    category = product.get('category_name', '미분류')
                    category_stats[category] = category_stats.get(category, 0) + 1

                logger.info("\n카테고리별 신규 상품:")
                for category, count in sorted(category_stats.items()):
                    logger.info(f"  - {category}: {count}개")

                # 샘플 상품 출력
                logger.info("\n신규 상품 샘플 (최대 5개):")
                for i, product in enumerate(new_products[:5], 1):
                    logger.info(f"  {i}. {product.get('item_name', 'N/A')}")
                    logger.info(f"     - goods_no: {product.get('goods_no', 'N/A')}")
                    logger.info(f"     - 브랜드: {product.get('brand_name', 'N/A')}")
                    logger.info(f"     - 가격: {product.get('price', 'N/A')}원")

                # 결과 저장
                storage.save(new_products)
                logger.info(f"\n결과 저장 완료: {storage.file_path}")
            else:
                logger.info("신규 상품이 없습니다.")

        except Exception as e:
            logger.error(f"최신 상품 크롤링 테스트 실행 중 오류: {str(e)}", exc_info=True)


async def test_full_crawling_flow(max_items_per_category: int = 2, category_filter_length: int = None, use_excel: bool = False):
    """
    전체 크롤링 플로우 테스트: 카테고리 추출 → 상품 ID 추출 → 상품 데이터 크롤링.

    Args:
        max_items_per_category: 카테고리당 최대 크롤링 개수
        category_filter_length: 카테고리 ID 길이 필터 (None이면 모든 길이)
        use_excel: Excel 저장소 사용 여부
    """
    logger.info("=== Oliveyoung 전체 크롤링 플로우 테스트 시작 ===")
    logger.info(f"카테고리당 최대 아이템: {max_items_per_category}")
    if category_filter_length:
        logger.info(f"카테고리 길이 필터: {category_filter_length}자리")
    storage_type = "Excel" if use_excel else "JSON"
    logger.info(f"저장소 타입: {storage_type}")
    
    # 저장소 생성
    storage = create_storage("oliveyoung_products", use_excel)
    
    async with OliveyoungCrawler(storage=storage) as crawler:
        try:
            # 1단계: 메인 페이지에서 모든 카테고리 ID 추출
            logger.info("1단계: 메인 페이지에서 카테고리 ID 추출 중...")
            all_categories = await crawler.extract_all_category_ids()
            
            if not all_categories:
                logger.error("카테고리 ID를 추출할 수 없습니다")
                return
            
            # 카테고리 필터링 (옵션)
            if category_filter_length:
                filtered_categories = []
                for cat in all_categories:
                    cat_id = cat["id"] if isinstance(cat, dict) else cat
                    if len(cat_id) == category_filter_length:
                        filtered_categories.append(cat)
                logger.info(f"카테고리 필터링: {len(all_categories)}개 → {len(filtered_categories)}개 (길이 {category_filter_length}자리)")
                all_categories = filtered_categories
            
            if not all_categories:
                logger.warning("필터링 후 크롤링할 카테고리가 없습니다")
                return
            
            # 모든 카테고리 사용
            target_categories = all_categories
            category_ids = [cat["id"] if isinstance(cat, dict) else cat for cat in target_categories]
            
            logger.info(f"크롤링 대상 카테고리: {len(target_categories)}개")
            if len(target_categories) <= 10:
                logger.info(f"카테고리 목록: {', '.join(category_ids)}")
            else:
                logger.info(f"처음 10개: {', '.join(category_ids[:10])}")
                logger.info(f"... 및 {len(target_categories) - 10}개 더")
            
            # 2단계: 각 카테고리에서 제품 ID 추출 및 크롤링
            all_products = []
            
            for i, category in enumerate(target_categories, 1):
                try:
                    category_id = category["id"] if isinstance(category, dict) else category
                    category_name = category.get("name", "Unknown") if isinstance(category, dict) else "Unknown"
                    
                    logger.info(f"2단계: 카테고리 {i}/{len(target_categories)} 처리 중 - {category_id} ({category_name})")
                    
                    # 카테고리에서 제품 크롤링 (crawl_from_category 사용)
                    category_products = await crawler.crawl_from_category(category_id, max_items_per_category)
                    
                    if category_products:
                        all_products.extend(category_products)
                        logger.info(f"카테고리 {category_id}: {len(category_products)}개 제품 크롤링 완료")
                        
                        # 크롤링된 제품 정보 출력 (처음 3개만)
                        for j, product in enumerate(category_products[:3], 1):
                            logger.info(f"  제품 {j}: {product.get('item_name', 'N/A')} - {product.get('price', 'N/A')}")
                        if len(category_products) > 3:
                            logger.info(f"  ... 및 {len(category_products) - 3}개 더")
                    else:
                        logger.warning(f"카테고리 {category_id}: 제품 크롤링 실패")
                    
                    # 카테고리 간 지연
                    if i < len(target_categories):
                        from crawler.utils import random_delay
                        await random_delay(5, 8)
                        logger.info(f"카테고리 간 지연 완료 (다음: {i + 1}/{len(target_categories)})")
                        
                except Exception as e:
                    logger.error(f"카테고리 {category_id} 처리 중 오류: {str(e)}")
                    continue
            
            # 4단계: 결과 정리
            logger.info("=== Oliveyoung 전체 크롤링 플로우 테스트 완료 ===")
            logger.info(f"총 처리된 카테고리: {len(target_categories)}개")
            logger.info(f"총 크롤링된 제품: {len(all_products)}개")
            
            if all_products:
                # 결과 저장
                storage.save(all_products)
                logger.info(f"결과 저장 완료: {storage.file_path}")
            
        except Exception as e:
            logger.error(f"전체 크롤링 플로우 테스트 실행 중 오류: {str(e)}", exc_info=True)


def main():
    """메인 함수."""
    parser = argparse.ArgumentParser(description="Oliveyoung 크롤러 테스트")
    parser.add_argument(
        "--goods-no",
        type=str,
        help="테스트할 goodsNo (단일 제품 테스트)",
        default=None
    )
    parser.add_argument(
        "--category-id",
        type=str,
        help="테스트할 카테고리 ID",
        default=None
    )
    parser.add_argument(
        "--max-items",
        type=int,
        help="최대 크롤링 아이템 수",
        default=10
    )
    parser.add_argument(
        "--test-extraction",
        action="store_true",
        help="goodsNo 추출만 테스트"
    )
    parser.add_argument(
        "--test-categories",
        action="store_true",
        help="카테고리 ID 추출 테스트"
    )
    parser.add_argument(
        "--full-flow",
        action="store_true",
        help="전체 크롤링 플로우 테스트"
    )
    parser.add_argument(
        "--category-filter",
        type=int,
        help="카테고리 ID 길이 필터 (전체 플로우에서 사용)",
        default=None
    )
    parser.add_argument(
        "--use-excel",
        action="store_true",
        help="Excel 저장소 사용 (기본값: JSON)"
    )
    parser.add_argument(
        "--test-filter",
        action="store_true",
        help="카테고리 필터링 기능 테스트"
    )
    parser.add_argument(
        "--filter-file",
        type=str,
        help="카테고리 필터링 단어가 저장된 파일 경로",
        default="category_filter.txt"
    )
    parser.add_argument(
        "--filter-words",
        type=str,
        nargs="+",
        help="카테고리 필터링 단어 (공백으로 구분)",
        default=None
    )
    parser.add_argument(
        "--output-filename",
        type=str,
        help="고정 출력 파일명 (예: oliveyoung_products.xlsx)",
        default=None
    )
    parser.add_argument(
        "--test-new-products",
        action="store_true",
        help="최신 상품만 크롤링 테스트 (--existing-excel 필수)"
    )
    parser.add_argument(
        "--existing-excel",
        type=str,
        help="기존 크롤링 결과 엑셀 파일 경로 (최신 상품 크롤링 시 사용)",
        default="data/oliveyoung_20250929.xlsx"
    )

    args = parser.parse_args()
    
    # 출력 디렉토리 생성
    Path("data").mkdir(exist_ok=True)
    
    try:
        if args.test_new_products:
            # 최신 상품만 크롤링 테스트
            if not Path(args.existing_excel).exists():
                logger.error(f"기존 엑셀 파일을 찾을 수 없습니다: {args.existing_excel}")
                logger.error("--existing-excel 옵션으로 올바른 파일 경로를 지정하세요.")
                return

            asyncio.run(test_new_products_only(
                existing_excel=args.existing_excel,
                max_items_per_category=args.max_items,
                use_excel=args.use_excel,
                output_filename=args.output_filename,
                filter_file=args.filter_file
            ))

        elif args.test_categories:
            # 카테고리 ID 추출 테스트 (저장소 불필요)
            asyncio.run(test_category_extraction())

        elif args.test_filter:
            # 카테고리 필터링 기능 테스트
            asyncio.run(test_category_filtering(
                filter_file=args.filter_file,
                filter_words=args.filter_words,
                max_items_per_category=args.max_items,
                use_excel=args.use_excel,
                output_filename=args.output_filename
            ))
            
        elif args.full_flow:
            # 전체 크롤링 플로우 테스트
            asyncio.run(test_full_crawling_flow(args.max_items, args.category_filter, args.use_excel))
            
        elif args.goods_no:
            # 단일 제품 테스트
            asyncio.run(test_single_product(args.goods_no, args.use_excel))
            
        elif args.category_id:
            if args.test_extraction:
                # goodsNo 추출만 테스트 (저장소 불필요)
                asyncio.run(test_goods_no_extraction(args.category_id, args.max_items))
            else:
                # 카테고리 크롤링 테스트
                asyncio.run(test_category_crawling(args.category_id, args.max_items, args.use_excel))
        else:
            # 기본 테스트 실행
            logger.info("기본 Oliveyoung 테스트를 실행합니다...")
            storage_type = "Excel" if args.use_excel else "JSON"
            logger.info(f"저장소 타입: {storage_type}")
            
            # 예시 goodsNo로 테스트 (실제 존재하는 상품 번호로 교체 필요)
            test_goods_no = "A000000192405"  # 예시 goodsNo
            asyncio.run(test_single_product(test_goods_no, args.use_excel))
            
    except KeyboardInterrupt:
        logger.info("사용자에 의해 테스트가 중단되었습니다.")
    except Exception as e:
        logger.error(f"테스트 실행 실패: {str(e)}", exc_info=True)


if __name__ == "__main__":
    main()
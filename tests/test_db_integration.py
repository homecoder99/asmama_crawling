"""
통합 테스트: 크롤링 → DB 저장 → 업로드 전체 워크플로우 테스트

단계:
1. Oliveyoung 카테고리에서 1개 상품만 크롤링
2. PostgreSQL에 저장 (dry-run 옵션 지원)
3. DB에서 데이터 로드하여 업로드 변환
"""

import asyncio
import os
import sys
from pathlib import Path
import logging
import argparse

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# .env 파일에서 환경변수 로드
def load_env():
    """Load environment variables from .env file."""
    env_file = project_root / '.env'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    os.environ[key] = value

# 환경변수 로드
load_env()

from crawler.oliveyoung import OliveyoungCrawler
from crawler.storage import ExcelStorage
from crawler.db_storage import PostgresStorage


# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DryRunStorage:
    """
    Dry-run 모드용 저장소.

    실제 DB에 저장하지 않고 메모리에만 저장한다.
    """

    def __init__(self):
        self.data = []
        self.logger = logging.getLogger(__name__)

    def save(self, data):
        """데이터를 메모리에 저장한다."""
        if isinstance(data, dict):
            self.data.append(data)
        else:
            self.data.extend(data)

        self.logger.info(f"[DRY-RUN] {len(data if isinstance(data, list) else [data])}개 항목 저장 (실제 DB 저장 안 함)")
        return True

    def load(self):
        """저장된 데이터를 반환한다."""
        return self.data

    def clear(self):
        """데이터를 초기화한다."""
        self.data = []
        return True

    def get_saved_data(self):
        """저장된 데이터를 반환한다."""
        return self.data


async def test_crawl_single_product(goods_no: str, dry_run: bool = True):
    """
    단일 제품 크롤링 테스트.

    Args:
        goods_no: Oliveyoung 제품 ID
        dry_run: True이면 실제 DB에 저장하지 않음

    Returns:
        크롤링된 제품 데이터
    """
    logger.info(f"=== 단계 1: 제품 크롤링 (goods_no={goods_no}, dry_run={dry_run}) ===")

    # 임시 엑셀 저장소 (크롤러는 엑셀 저장소 필요)
    excel_path = project_root / "data" / "test_integration.xlsx"
    excel_storage = ExcelStorage(str(excel_path))

    # DB 저장소 설정
    if dry_run:
        db_storage = DryRunStorage()
        logger.info("Dry-run 모드: 메모리 저장소 사용")
    else:
        if not os.getenv("DATABASE_URL"):
            raise ValueError("실제 DB 저장 시 DATABASE_URL 환경변수가 필요합니다.")
        db_storage = PostgresStorage()
        logger.info("실제 모드: PostgreSQL 저장소 사용")

    # 크롤러 실행
    async with OliveyoungCrawler(storage=excel_storage, db_storage=db_storage) as crawler:
        product = await crawler.crawl_single_product(goods_no)

        if not product:
            logger.error("크롤링 실패")
            return None

        logger.info(f"크롤링 성공: {product.get('name', product.get('item_name', 'Unknown'))}")
        logger.info(f"  - goods_no: {product.get('branduid', product.get('goods_no', 'Unknown'))}")
        logger.info(f"  - price: {product.get('price', 0)}")
        logger.info(f"  - brand: {product.get('brand_name', 'Unknown')}")

        # 수동으로 저장 (crawl_single_product는 저장하지 않음)
        if excel_storage:
            excel_storage.save(product)
            logger.info("엑셀 저장 완료")

        if db_storage:
            db_storage.save(product)
            logger.info(f"{'Dry-run ' if dry_run else ''}DB 저장 완료")

    # Dry-run 모드인 경우 저장된 데이터 반환
    if dry_run and hasattr(db_storage, 'get_saved_data'):
        saved_data = db_storage.get_saved_data()
        logger.info(f"Dry-run 저장소에 {len(saved_data)}개 항목 저장됨")
        return saved_data[0] if saved_data else None

    return product


async def test_crawl_category(category_id: str, max_items: int = 1, dry_run: bool = True):
    """
    카테고리에서 N개 제품 크롤링 테스트.

    Args:
        category_id: Oliveyoung 카테고리 ID
        max_items: 최대 크롤링 개수
        dry_run: True이면 실제 DB에 저장하지 않음

    Returns:
        크롤링된 제품 리스트
    """
    logger.info(f"=== 단계 1: 카테고리 크롤링 (category_id={category_id}, max_items={max_items}, dry_run={dry_run}) ===")

    # 임시 엑셀 저장소
    excel_path = project_root / "data" / "test_integration.xlsx"
    excel_storage = ExcelStorage(str(excel_path))

    # DB 저장소 설정
    if dry_run:
        db_storage = DryRunStorage()
        logger.info("Dry-run 모드: 메모리 저장소 사용")
    else:
        if not os.getenv("DATABASE_URL"):
            raise ValueError("실제 DB 저장 시 DATABASE_URL 환경변수가 필요합니다.")
        db_storage = PostgresStorage()
        logger.info("실제 모드: PostgreSQL 저장소 사용")

    # 크롤러 실행
    async with OliveyoungCrawler(storage=excel_storage, db_storage=db_storage) as crawler:
        products = await crawler.crawl_from_category(category_id, max_items)

        if not products:
            logger.error("크롤링 실패")
            return []

        logger.info(f"크롤링 성공: {len(products)}개 제품")
        for i, product in enumerate(products, 1):
            logger.info(f"  {i}. {product.get('name', product.get('item_name', 'Unknown'))} - {product.get('price', 0)}원")

    # Dry-run 모드인 경우 저장된 데이터 반환
    if dry_run and hasattr(db_storage, 'get_saved_data'):
        saved_data = db_storage.get_saved_data()
        logger.info(f"Dry-run 저장소에 {len(saved_data)}개 항목 저장됨")
        return saved_data

    return products


def test_upload_from_db(dry_run: bool = True, source_type: str = "memory", dry_run_data=None):
    """
    DB에서 데이터를 로드하여 업로드 변환 테스트.

    Args:
        dry_run: True이면 실제 DB 읽지 않고 dry_run_data 사용
        source_type: "memory" 또는 "postgres"
        dry_run_data: dry-run 모드에서 사용할 데이터

    Returns:
        변환 성공 여부
    """
    logger.info(f"=== 단계 2: 업로드 변환 (source_type={source_type}, dry_run={dry_run}) ===")

    # uploader 모듈 임포트
    uploader_path = project_root / "uploader"
    if str(uploader_path) not in sys.path:
        sys.path.insert(0, str(uploader_path))

    try:
        from oliveyoung_uploader import OliveyoungUploader
        from data_adapter import PostgresDataAdapter
        from qoo10_db_storage import Qoo10ProductsStorage
        import pandas as pd
    except ImportError as e:
        logger.error(f"모듈 임포트 실패: {e}")
        return False

    # Uploader 초기화
    templates_dir = project_root / "uploader" / "templates"
    output_dir = project_root / "data" / "test_output"

    # qoo10_products DB 저장소 (실제 DB 모드인 경우)
    qoo10_db_storage = None
    if source_type == "postgres" and not dry_run:
        try:
            qoo10_db_storage = Qoo10ProductsStorage()
            logger.info("qoo10_products DB 저장소 활성화됨")
        except Exception as e:
            logger.error(f"qoo10_products DB 저장소 초기화 실패: {e}")

    uploader = OliveyoungUploader(
        templates_dir=str(templates_dir),
        output_dir=str(output_dir),
        image_filter_mode="none",  # 테스트에서는 이미지 필터링 생략
        db_storage=qoo10_db_storage  # qoo10_products 저장용
    )

    # 템플릿 로딩
    if not uploader.load_templates():
        logger.error("템플릿 로딩 실패")
        return False

    logger.info("템플릿 로딩 완료")

    # 데이터 로딩
    if source_type == "memory" and dry_run_data is not None:
        # 단일 dict인 경우 리스트로 변환
        if isinstance(dry_run_data, dict):
            dry_run_data = [dry_run_data]

        # Dry-run 데이터를 DataFrame으로 변환
        logger.info(f"Dry-run 데이터 사용: {len(dry_run_data)}개 항목")

        # 크롤러 스키마 → 엑셀 스키마 변환
        for item in dry_run_data:
            if isinstance(item, dict):
                if 'branduid' not in item and 'goods_no' in item:
                    item['branduid'] = item['goods_no']
                if 'name' not in item and 'item_name' in item:
                    item['name'] = item['item_name']

        df = pd.DataFrame(dry_run_data)
        products = df.to_dict('records')

    elif source_type == "postgres" and not dry_run:
        # 실제 DB에서 로딩
        logger.info("PostgreSQL에서 데이터 로딩 중...")

        adapter = PostgresDataAdapter(source_filter="oliveyoung")
        df = adapter.load_products()
        products = df.to_dict('records')

        logger.info(f"PostgreSQL에서 {len(products)}개 제품 로딩 완료")
    else:
        logger.error(f"잘못된 조합: source_type={source_type}, dry_run={dry_run}")
        return False

    if not products:
        logger.warning("로드된 데이터가 없습니다.")
        return False

    logger.info(f"업로드 변환 대상: {len(products)}개 제품")
    for i, product in enumerate(products[:3], 1):  # 처음 3개만 출력
        logger.info(f"  {i}. {product.get('name', product.get('item_name', 'Unknown'))} - {product.get('price', 0)}원")

    # 실제 변환 수행 (dry_run이 아닌 경우)
    if not dry_run and source_type == "postgres":
        logger.info("실제 업로드 변환 수행 중...")

        # process_crawled_data 호출
        success = uploader.process_crawled_data(
            source_type='postgres',
            source_filter='oliveyoung'
        )

        if success:
            logger.info("✅ 업로드 변환 및 qoo10_products 저장 성공!")
        else:
            logger.error("❌ 업로드 변환 실패")

        return success
    else:
        logger.info("업로드 변환 테스트 완료 (dry-run 모드)")
        return True


def verify_dry_run_data(products):
    """
    Dry-run 데이터 검증.

    Args:
        products: 크롤링된 제품 리스트

    Returns:
        검증 통과 여부
    """
    logger.info("=== Dry-run 데이터 검증 ===")

    if not products:
        logger.error("데이터가 없습니다.")
        return False

    # 단일 제품인 경우 리스트로 변환
    if isinstance(products, dict):
        products = [products]

    # 필수 필드 검증
    required_fields = ['branduid', 'name', 'price']

    for i, product in enumerate(products, 1):
        logger.info(f"제품 {i} 검증:")

        # 필드 존재 여부 확인
        for field in required_fields:
            # branduid는 goods_no로도 대체 가능
            if field == 'branduid' and 'goods_no' in product:
                logger.info(f"  ✓ {field} (goods_no): {product['goods_no']}")
            # name은 item_name으로도 대체 가능
            elif field == 'name' and 'item_name' in product:
                logger.info(f"  ✓ {field} (item_name): {product['item_name']}")
            elif field in product:
                logger.info(f"  ✓ {field}: {product[field]}")
            else:
                logger.error(f"  ✗ {field}: 필드 누락")
                return False

        # 추가 필드 확인
        if 'image_urls' in product or 'images' in product:
            image_field = 'image_urls' if 'image_urls' in product else 'images'
            logger.info(f"  ✓ {image_field}: {len(product[image_field]) if isinstance(product[image_field], list) else 1}개")

        if 'options' in product or 'option_info' in product:
            logger.info(f"  ✓ options/option_info: 존재")

    logger.info("검증 통과!")
    return True


async def main():
    """메인 테스트 함수."""
    parser = argparse.ArgumentParser(description="DB 통합 테스트")
    parser.add_argument(
        "--mode",
        choices=["single", "category"],
        default="single",
        help="테스트 모드: single (단일 제품) 또는 category (카테고리)"
    )
    parser.add_argument(
        "--goods-no",
        default="A000000192405",
        help="단일 제품 테스트 시 goods_no (기본값: A000000192405)"
    )
    parser.add_argument(
        "--category-id",
        default="100000100010001",
        help="카테고리 테스트 시 category_id (기본값: 100000100010001)"
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=1,
        help="카테고리 테스트 시 최대 크롤링 개수 (기본값: 1)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Dry-run 모드 (실제 DB에 저장하지 않음, 기본값: True)"
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="실제 DB에 저장 (--dry-run을 무시)"
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="업로드 변환 단계 건너뛰기"
    )

    args = parser.parse_args()

    # --real 옵션이 주어지면 dry-run을 False로 설정
    dry_run = not args.real

    logger.info("=" * 70)
    logger.info("DB 통합 테스트 시작")
    logger.info(f"모드: {args.mode}")
    logger.info(f"Dry-run: {dry_run}")
    logger.info("=" * 70)

    # 1단계: 크롤링
    if args.mode == "single":
        products = await test_crawl_single_product(args.goods_no, dry_run=dry_run)
    else:  # category
        products = await test_crawl_category(args.category_id, args.max_items, dry_run=dry_run)

    if not products:
        logger.error("크롤링 실패")
        return False

    # Dry-run인 경우 검증
    if dry_run:
        if not verify_dry_run_data(products):
            logger.error("데이터 검증 실패")
            return False

        logger.info("\n검증 완료! 실제 DB에 저장하려면 --real 옵션을 추가하세요.")

        # 사용자 확인
        if not args.skip_upload:
            response = input("\n업로드 변환 테스트를 진행하시겠습니까? (y/n): ")
            if response.lower() != 'y':
                logger.info("업로드 변환 테스트 건너뛰기")
                return True

    # 2단계: 업로드 변환 (옵션)
    if not args.skip_upload:
        source_type = "memory" if dry_run else "postgres"
        dry_run_data = products if dry_run else None

        success = test_upload_from_db(
            dry_run=dry_run,
            source_type=source_type,
            dry_run_data=dry_run_data
        )

        if not success:
            logger.error("업로드 변환 실패")
            return False

    logger.info("\n" + "=" * 70)
    logger.info("통합 테스트 완료!")
    logger.info("=" * 70)

    return True


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        logger.info("\n테스트 중단")
        sys.exit(1)
    except Exception as e:
        logger.error(f"테스트 실패: {str(e)}", exc_info=True)
        sys.exit(1)

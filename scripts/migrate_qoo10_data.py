"""
Qoo10 데이터 마이그레이션 스크립트

data/ 와 output/ 폴더의 데이터를 PostgreSQL로 로드합니다:
- data/qoo10_*.xlsx → qoo10_products 테이블

사용법:
    python scripts/migrate_qoo10_data.py --db-url postgresql://user:pass@localhost/dbname
    python scripts/migrate_qoo10_data.py --dry-run  # 테스트 실행
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/qoo10_migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class Qoo10DataMigrator:
    """Qoo10 데이터 마이그레이션 클래스"""

    def __init__(self, db_url: str, dry_run: bool = False):
        """
        Args:
            db_url: PostgreSQL 연결 URL
            dry_run: True일 경우 DB에 쓰지 않고 로그만 출력
        """
        self.db_url = db_url
        self.dry_run = dry_run
        self.conn = None
        self.stats = {
            'products_inserted': 0,
            'errors': 0
        }

    def __enter__(self):
        if not self.dry_run:
            self.conn = psycopg2.connect(self.db_url)
            self.conn.autocommit = False
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type is None:
                self.conn.commit()
                logger.info("트랜잭션 커밋 완료")
            else:
                self.conn.rollback()
                logger.error(f"트랜잭션 롤백: {exc_val}")
            self.conn.close()

    def migrate_qoo10_products(self, file_path: Path) -> None:
        """
        Qoo10 제품 데이터를 qoo10_products 테이블에 로드

        Args:
            file_path: Qoo10 제품 데이터 파일 경로
        """
        logger.info(f"=== Qoo10 제품 데이터 마이그레이션 시작: {file_path} ===")

        try:
            # 5행(1-based)을 헤더로 사용해 읽기
            df = pd.read_excel(file_path, header=0, skiprows=range(1,4), dtype=str)

            logger.info(f"총 {len(df)}개 제품 로드")
            logger.info(f"컬럼: {df.columns.tolist()}")

            if self.dry_run:
                logger.info(f"[DRY RUN] 샘플 데이터:\n{df.head()}")
                return

            # INSERT 쿼리 (ON CONFLICT DO NOTHING - 중복 방지)
            query = """
                INSERT INTO qoo10_products (
                    item_number, seller_unique_item_id, category_number, brand_number, item_name,
                    price_yen, image_main_url, item_description, item_name_ja, item_name_en,
                    item_name_zh, search_keywords, model_name, manufacturer, origin_country,
                    material, color, size, weight, volume, age_group, gender, season, expiry_date,
                    manufacture_date, certification_info, caution_info, storage_method, usage_method,
                    ingredients, nutritional_info, warranty_info, as_info, shipping_method, shipping_fee,
                    return_shipping_fee, exchange_info, refund_info, available_coupon, available_point,
                    tax_type, additional_images, detail_images, option_type, option_info, stock_quantity,
                    min_order_quantity, max_order_quantity, source_crawled_product_id
                )
                VALUES %s
                ON CONFLICT (seller_unique_item_id) DO NOTHING
            """

            # NULL 값 처리
            df = df.fillna({
                'item_number': '',
                'item_name_ja': '',
                'item_name_en': '',
                'item_name_zh': '',
                'search_keywords': '',
                'model_name': '',
                'manufacturer': '',
                'origin_country': '',
                'material': '',
                'color': '',
                'size': '',
                'weight': '',
                'volume': '',
                'age_group': '',
                'gender': '',
                'season': '',
                'expiry_date': '',
                'manufacture_date': '',
                'certification_info': '',
                'caution_info': '',
                'storage_method': '',
                'usage_method': '',
                'ingredients': '',
                'nutritional_info': '',
                'warranty_info': '',
                'as_info': '',
                'shipping_method': '',
                'exchange_info': '',
                'refund_info': '',
                'additional_images': '',
                'detail_images': '',
                'option_type': '',
                'option_info': '',
            })

            values = []
            for i, row in df.iterrows():

                # brand_number는 비어있으면 NULL로(=None) → FK 통과
                brand_value = row.get('brand_number')
                if brand_value is None or str(brand_value).strip().lower() in ('', 'nan', 'none', 'null'):
                    brand_value = None
            
                values.append((
                    row['item_number'],
                    row['seller_unique_item_id'],
                    row['category_number'],     # NOT NULL/FK: 파일에 값 있어야 함
                    brand_value,                # brand_number는 비어있으면 NULL로(=None) → FK 통과
                    row['item_name'],
                    row['price_yen'],
                    row['image_main_url'],
                    row['item_description'],
                    row.get('item_name_ja'),
                    row.get('item_name_en'),
                    row.get('item_name_zh'),
                    row.get('search_keywords'),
                    row.get('model_name'),
                    row.get('manufacturer'),
                    row.get('origin_country'),
                    row.get('material'),
                    row.get('color'),
                    row.get('size'),
                    row.get('weight'),
                    row.get('volume'),
                    row.get('age_group'),
                    row.get('gender'),
                    row.get('season'),
                    row.get('expiry_date'),
                    row.get('manufacture_date'),
                    row.get('certification_info'),
                    row.get('caution_info'),
                    row.get('storage_method'),
                    row.get('usage_method'),
                    row.get('ingredients'),
                    row.get('nutritional_info'),
                    row.get('warranty_info'),
                    row.get('as_info'),
                    row.get('shipping_method'),
                    row.get('shipping_fee'),
                    row.get('return_shipping_fee'),
                    row.get('exchange_info'),
                    row.get('refund_info'),
                    row.get('available_coupon'),
                    row.get('available_point'),
                    row.get('tax_type'),
                    row.get('additional_images'),
                    row.get('detail_images'),
                    row.get('option_type'),
                    row.get('option_info'),
                    row.get('stock_quantity'),
                    row.get('min_order_quantity'),
                    row.get('max_order_quantity'),
                    row.get('source_crawled_product_id'),
                ))
               
            with self.conn.cursor() as cur:
                # 삽입 전 개수 확인
                cur.execute("SELECT COUNT(*) FROM qoo10_products")
                count_before = cur.fetchone()[0]

                # 데이터 삽입
                execute_values(cur, query, values)

                # 삽입 후 개수 확인
                cur.execute("SELECT COUNT(*) FROM qoo10_products")
                count_after = cur.fetchone()[0]

                inserted_count = count_after - count_before
                self.stats['products_inserted'] = inserted_count

            logger.info(f"✓ {inserted_count}개 제품 저장 완료 (중복 제외)")
            logger.info(f"  스킵된 중복: {len(values) - inserted_count}개")

        except Exception as e:
            logger.error(f"✗ Qoo10 제품 마이그레이션 실패: {e}")
            self.stats['errors'] += 1
            raise
    
    def print_stats(self) -> None:
        """마이그레이션 통계 출력"""
        logger.info("\n" + "="*50)
        logger.info("Qoo10 제품 마이그레이션 통계")
        logger.info("="*50)
        logger.info(f"제품 삽입: {self.stats['products_inserted']}개")  
        logger.info(f"에러 발생: {self.stats['errors']}건")
        logger.info("="*50)

def main():
    parser = argparse.ArgumentParser(description='Qoo10 제품 데이터 마이그레이션')
    parser.add_argument(
        '--db-url',
        default='postgresql://postgres:password@localhost:5432/marketfeat',
        help='PostgreSQL 연결 URL'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='실제 DB에 쓰지 않고 테스트만 실행'
    )

    args = parser.parse_args()

    # 파일 경로 설정
    base_dir = Path(__file__).parent.parent

    # 가장 최신 파일 찾기
    data_dir = base_dir / 'output'

    product_files = list(data_dir.glob('qoo10_*.xlsx'))

    if not product_files:
        logger.error(f"제품 데이터 파일을 찾을 수 없습니다: {data_dir}/qoo10_*.xlsx")
        sys.exit(1)

    # 최신 파일 선택 (파일명 정렬)
    product_file = sorted(product_files)[-1]

    logger.info(f"제품 데이터 파일: {product_file}")

    try:
        with Qoo10DataMigrator(args.db_url, args.dry_run) as migrator:
            if args.dry_run:
                logger.warning("⚠️  DRY RUN 모드: 실제 DB에 쓰지 않습니다")

            # 제품 데이터 마이그레이션
            migrator.migrate_qoo10_products(product_file)

            migrator.print_stats()

            if not args.dry_run:
                logger.info("✓ Qoo10 제품 마이그레이션 완료!")

    except Exception as e:
        logger.error(f"✗ 마이그레이션 실패: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

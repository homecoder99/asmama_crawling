"""
크롤링된 데이터 마이그레이션 스크립트

data/ 와 output/ 폴더의 데이터를 PostgreSQL로 로드합니다:
- data/oliveyoung_*.xlsx → crawled_products 테이블
- output/failed_brands_*.csv → brand_mapping_logs 테이블

사용법:
    python scripts/migrate_crawled_data.py --db-url postgresql://user:pass@localhost/dbname
    python scripts/migrate_crawled_data.py --dry-run  # 테스트 실행
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
        logging.FileHandler(f'logs/crawl_migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class CrawledDataMigrator:
    """크롤링 데이터 마이그레이션 클래스"""

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
            'failed_brands_inserted': 0,
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

    def migrate_crawled_products(self, file_path: Path) -> None:
        """
        크롤링된 제품 데이터를 crawled_products 테이블에 로드

        Args:
            file_path: oliveyoung 크롤링 데이터 파일 경로
        """
        logger.info(f"=== 크롤링 제품 데이터 마이그레이션 시작: {file_path} ===")

        try:
            df = pd.read_excel(file_path)
            logger.info(f"총 {len(df)}개 제품 로드")
            logger.info(f"컬럼: {df.columns.tolist()}")

            if self.dry_run:
                logger.info(f"[DRY RUN] 샘플 데이터:\n{df.head()}")
                return

            # INSERT 쿼리 (ON CONFLICT DO NOTHING - 중복 방지)
            query = """
                INSERT INTO crawled_products (
                    price, goods_no, item_name, brand_name, origin_price,
                    is_discounted, discount_info, benefit_info, shipping_info, refund_info,
                    is_soldout, images, is_option_available, unique_item_id, source,
                    origin_product_url, others, option_info, discount_start_date, discount_end_date,
                    manufacturer, origin_country, category_main, category_sub, category_detail,
                    category_main_id, category_sub_id, category_detail_id, category_name, crawled_at, created_at
                )
                VALUES %s
                ON CONFLICT (unique_item_id) DO NOTHING
            """

            # NULL 값 처리
            df = df.fillna({
                'discount_info': '',
                'others': '',
                'option_info': '',
                'discount_start_date': '',
                'discount_end_date': '',
                'manufacturer': '',
                'origin_country': '',
                'category_main': '',
                'category_sub': '',
                'category_detail': '',
                'category_main_id': '',
                'category_sub_id': '',
                'category_detail_id': '',
                'category_name': ''
            })

            values = []
            for _, row in df.iterrows():
                # category_*_id는 VARCHAR로 변환 (scientific notation 방지)
                def safe_category_id(val):
                    if pd.notna(val) and val != '':
                        try:
                            return str(int(float(val)))
                        except:
                            return str(val)
                    return None

                values.append((
                    int(row['price']),
                    row['goods_no'],
                    row['item_name'],
                    row['brand_name'],
                    int(row['origin_price']),
                    bool(row['is_discounted']),
                    row['discount_info'] if row['discount_info'] else None,
                    row['benefit_info'],
                    row['shipping_info'],
                    row['refund_info'],
                    bool(row['is_soldout']),
                    row['images'],  # '|' delimited
                    bool(row['is_option_available']),
                    row['unique_item_id'],
                    row['source'],
                    row['origin_product_url'],
                    row['others'] if row['others'] else None,
                    row['option_info'] if row['option_info'] else None,  # '||*' delimited
                    row['discount_start_date'] if row['discount_start_date'] else None,
                    row['discount_end_date'] if row['discount_end_date'] else None,
                    row['manufacturer'] if row['manufacturer'] else None,
                    row['origin_country'] if row['origin_country'] else None,
                    row['category_main'] if row['category_main'] else None,
                    row['category_sub'] if row['category_sub'] else None,
                    row['category_detail'] if row['category_detail'] else None,
                    safe_category_id(row['category_main_id']),
                    safe_category_id(row['category_sub_id']),
                    safe_category_id(row['category_detail_id']),
                    row['category_name'] if row['category_name'] else None,
                    datetime.now(),  # crawled_at
                    datetime.now()   # created_at
                ))

            with self.conn.cursor() as cur:
                # 삽입 전 개수 확인
                cur.execute("SELECT COUNT(*) FROM crawled_products")
                count_before = cur.fetchone()[0]

                # 데이터 삽입
                execute_values(cur, query, values)

                # 삽입 후 개수 확인
                cur.execute("SELECT COUNT(*) FROM crawled_products")
                count_after = cur.fetchone()[0]

                inserted_count = count_after - count_before
                self.stats['products_inserted'] = inserted_count

            logger.info(f"✓ {inserted_count}개 제품 저장 완료 (중복 제외)")
            logger.info(f"  스킵된 중복: {len(values) - inserted_count}개")

        except Exception as e:
            logger.error(f"✗ 크롤링 제품 마이그레이션 실패: {e}")
            self.stats['errors'] += 1
            raise

    def migrate_failed_brands(self, file_path: Path) -> None:
        """
        브랜드 매핑 실패 로그를 brand_mapping_logs 테이블에 로드

        Args:
            file_path: failed_brands CSV 파일 경로
        """
        logger.info(f"=== 브랜드 매핑 실패 로그 마이그레이션 시작: {file_path} ===")

        try:
            df = pd.read_csv(file_path)
            logger.info(f"총 {len(df)}개 실패 기록 로드")

            if self.dry_run:
                logger.info(f"[DRY RUN] 샘플 데이터:\n{df.head()}")
                return

            # INSERT 쿼리 (ON CONFLICT 제거 - PK가 id만 있음)
            query = """
                INSERT INTO brand_mapping_logs (
                    product_id, korean_brand, english_translation,
                    japanese_translation, resolved, failed_at, created_at
                )
                VALUES %s
            """

            values = [
                (
                    row['상품ID'],
                    row['원본_브랜드명'],
                    row['영어_번역'],
                    row['일본어_번역'],
                    False,  # resolved (나중에 브랜드 추가 시 업데이트)
                    pd.to_datetime(row['실패_시간']),
                    datetime.now()
                )
                for _, row in df.iterrows()
            ]

            with self.conn.cursor() as cur:
                execute_values(cur, query, values)
                self.stats['failed_brands_inserted'] = cur.rowcount

            logger.info(f"✓ {self.stats['failed_brands_inserted']}개 실패 기록 저장 완료")

            # 실패 브랜드 통계
            unique_brands = df['원본_브랜드명'].nunique()
            logger.info(f"  고유 실패 브랜드: {unique_brands}개")

        except Exception as e:
            logger.error(f"✗ 브랜드 매핑 실패 로그 마이그레이션 실패: {e}")
            self.stats['errors'] += 1
            raise

    def print_stats(self) -> None:
        """마이그레이션 통계 출력"""
        logger.info("\n" + "="*50)
        logger.info("크롤링 데이터 마이그레이션 통계")
        logger.info("="*50)
        logger.info(f"제품 삽입: {self.stats['products_inserted']}개")
        logger.info(f"브랜드 매핑 실패 로그: {self.stats['failed_brands_inserted']}개")
        logger.info(f"에러 발생: {self.stats['errors']}건")
        logger.info("="*50)


def main():
    parser = argparse.ArgumentParser(description='크롤링 데이터 마이그레이션')
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
    parser.add_argument(
        '--skip-products',
        action='store_true',
        help='제품 데이터 마이그레이션 건너뛰기'
    )
    parser.add_argument(
        '--skip-failed-brands',
        action='store_true',
        help='실패 브랜드 로그 마이그레이션 건너뛰기'
    )

    args = parser.parse_args()

    # 파일 경로 설정
    base_dir = Path(__file__).parent.parent

    # 가장 최신 파일 찾기
    data_dir = base_dir / 'data'
    output_dir = base_dir / 'output'

    product_files = list(data_dir.glob('oliveyoung_*.xlsx'))
    failed_brand_files = list(output_dir.glob('failed_brands_*.csv'))

    if not product_files:
        logger.error(f"제품 데이터 파일을 찾을 수 없습니다: {data_dir}/oliveyoung_*.xlsx")
        sys.exit(1)

    if not failed_brand_files:
        logger.warning(f"브랜드 매핑 실패 파일을 찾을 수 없습니다: {output_dir}/failed_brands_*.csv")

    # 최신 파일 선택 (파일명 정렬)
    product_file = sorted(product_files)[-1]
    failed_brand_file = sorted(failed_brand_files)[-1] if failed_brand_files else None

    logger.info(f"제품 데이터 파일: {product_file}")
    if failed_brand_file:
        logger.info(f"실패 브랜드 파일: {failed_brand_file}")

    try:
        with CrawledDataMigrator(args.db_url, args.dry_run) as migrator:
            if args.dry_run:
                logger.warning("⚠️  DRY RUN 모드: 실제 DB에 쓰지 않습니다")

            # 제품 데이터 마이그레이션
            if not args.skip_products:
                migrator.migrate_crawled_products(product_file)

            # 브랜드 매핑 실패 로그 마이그레이션
            if not args.skip_failed_brands and failed_brand_file:
                migrator.migrate_failed_brands(failed_brand_file)

            migrator.print_stats()

            if not args.dry_run:
                logger.info("✓ 크롤링 데이터 마이그레이션 완료!")

    except Exception as e:
        logger.error(f"✗ 마이그레이션 실패: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

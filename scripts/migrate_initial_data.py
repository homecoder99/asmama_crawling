"""
초기 데이터 마이그레이션 스크립트

Excel/CSV 파일에서 PostgreSQL로 데이터를 로드합니다:
1. brand.csv → brands (Qoo10 공식 브랜드, 영어/일본어 이름, brand_no)
2. brand_translations.csv → brands (한국어 브랜드명 추가)
3. ban.xlsx → brands (Qoo10에 있는 브랜드만 is_banned=TRUE로 업데이트)
4. Qoo10_CategoryInfo.csv → categories

사용법:
    python scripts/migrate_initial_data.py --db-url postgresql://user:pass@localhost/dbname
    python scripts/migrate_initial_data.py --dry-run  # 테스트 실행
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DataMigrator:
    """데이터 마이그레이션 클래스"""

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
            'qoo10_brands_inserted': 0,
            'korean_names_added': 0,
            'brands_banned': 0,
            'ban_not_in_qoo10': 0,
            'categories_inserted': 0,
            'errors': 0
        }
        self.qoo10_brand_titles = set()  # Qoo10 브랜드명 캐시

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

    def migrate_ban_brands(self, file_path: Path) -> None:
        """
        ban.xlsx에서 금지 브랜드를 읽고, Qoo10에 있는 브랜드만 is_banned=TRUE로 업데이트
        Qoo10에 없는 금지 브랜드는 로그만 남김

        Args:
            file_path: ban.xlsx 파일 경로
        """
        logger.info(f"=== 금지 브랜드 마이그레이션 시작: {file_path} ===")

        try:
            df = pd.read_excel(file_path)
            logger.info(f"총 {len(df)}개 행 로드")

            # brand 컬럼만 사용 (고유값 추출)
            banned_brands = df['brand'].dropna().unique()
            logger.info(f"고유 금지 브랜드: {len(banned_brands)}개")

            if self.dry_run:
                logger.info(f"[DRY RUN] 샘플 데이터: {banned_brands[:5]}")
                logger.info(f"[DRY RUN] Qoo10 캐시 브랜드 수: {len(self.qoo10_brand_titles)}개")
                return

            # Qoo10 브랜드 중에서 금지된 것만 필터링
            brands_to_ban = []
            brands_not_in_qoo10 = []

            for brand in banned_brands:
                # 대소문자 무시, 공백 제거하여 비교
                normalized_brand = brand.lower().replace(' ', '')

                # Qoo10 브랜드 중 매칭되는 것 찾기
                matched = False
                for qoo10_brand in self.qoo10_brand_titles:
                    if qoo10_brand.lower().replace(' ', '') == normalized_brand:
                        brands_to_ban.append(qoo10_brand)
                        matched = True
                        break

                if not matched:
                    brands_not_in_qoo10.append(brand)
                    logger.warning(f"⚠️  금지 브랜드가 Qoo10에 없음: {brand}")

            logger.info(f"Qoo10에 있는 금지 브랜드: {len(brands_to_ban)}개")
            logger.info(f"Qoo10에 없는 금지 브랜드: {len(brands_not_in_qoo10)}개 (로그만 남김)")

            # Qoo10에 있는 브랜드만 is_banned=TRUE로 업데이트
            if brands_to_ban:
                query = """
                    UPDATE brands
                    SET is_banned = TRUE, updated_at = CURRENT_TIMESTAMP
                    WHERE brand_title = ANY(%s) OR korean_name = ANY(%s)
                """

                with self.conn.cursor() as cur:
                    cur.execute(query, (brands_to_ban, brands_to_ban))
                    self.stats['brands_banned'] = cur.rowcount

            self.stats['ban_not_in_qoo10'] = len(brands_not_in_qoo10)
            logger.info(f"✓ {self.stats['brands_banned']}개 브랜드를 금지 처리 완료")

        except Exception as e:
            logger.error(f"✗ 금지 브랜드 마이그레이션 실패: {e}")
            self.stats['errors'] += 1
            raise

    def migrate_qoo10_brands(self, file_path: Path) -> None:
        """
        brand.csv에서 Qoo10 공식 브랜드 로드 (1단계: 기본 브랜드 정보)
        한국어 이름은 없고, 영어/일본어 브랜드명과 brand_no만 있음

        Args:
            file_path: brand.csv 파일 경로
        """
        logger.info(f"=== 1단계: Qoo10 브랜드 마이그레이션 시작: {file_path} ===")

        try:
            # BOM 인코딩 처리
            df = pd.read_csv(file_path, encoding='utf-8-sig')
            logger.info(f"총 {len(df)}개 브랜드 로드")

            if self.dry_run:
                logger.info(f"[DRY RUN] 샘플 데이터:\n{df.head()}")
                return

            # INSERT 쿼리 (ON CONFLICT DO NOTHING - 이미 있으면 스킵)
            query = """
                INSERT INTO brands (
                    brand_no, brand_title, english_name, japanese_name,
                    is_banned, is_qoo10_official, translation_source, translation_date, created_at
                )
                VALUES %s
                ON CONFLICT (brand_no) DO NOTHING
            """

            # NULL 값 처리 및 데이터 변환
            df = df.fillna('')
            values = []
            for _, row in df.iterrows():
                brand_title = row['Brand Title']
                self.qoo10_brand_titles.add(brand_title)  # 캐시에 추가

                values.append((
                    str(row['Brand No']),
                    brand_title,
                    row['English'] if row['English'] else None,
                    row['Japanese'] if row['Japanese'] else None,
                    False,  # is_banned (기본값, 나중에 ban.xlsx에서 업데이트)
                    True,   # is_qoo10_official
                    'qoo10',
                    datetime.now().date(),
                    datetime.now()
                ))

            with self.conn.cursor() as cur:
                execute_values(cur, query, values)
                self.stats['qoo10_brands_inserted'] = len(values)

            logger.info(f"✓ {len(values)}개 Qoo10 브랜드 저장 완료")
            logger.info(f"  (한국어 이름 없음 - 다음 단계에서 추가 예정)")

        except Exception as e:
            logger.error(f"✗ Qoo10 브랜드 마이그레이션 실패: {e}")
            self.stats['errors'] += 1
            raise

    def migrate_brand_translations(self, file_path: Path) -> None:
        """
        brand_translations.csv에서 한국어 브랜드명을 읽어 기존 Qoo10 브랜드에 추가
        영어/일본어 번역으로 매칭하여 korean_name 업데이트

        Args:
            file_path: brand_translations.csv 파일 경로
        """
        logger.info(f"=== 2단계: 브랜드 번역(한국어 이름) 추가 시작: {file_path} ===")

        try:
            df = pd.read_csv(file_path)
            logger.info(f"총 {len(df)}개 번역 로드")

            if self.dry_run:
                logger.info(f"[DRY RUN] 샘플 데이터:\n{df.head()}")
                return

            # 영어/일본어 이름으로 매칭하여 korean_name 업데이트
            updated_count = 0
            not_matched_count = 0
            not_matched_brands = []  # 매칭 실패한 브랜드 수집

            with self.conn.cursor() as cur:
                for _, row in df.iterrows():
                    korean_brand = row['korean_brand']
                    english_brand = row['english_brand']
                    japanese_brand = row['japanese_brand']

                    # 영어 또는 일본어 이름으로 매칭 (대소문자 무시, 공백 제거)
                    query = """
                        UPDATE brands
                        SET
                            korean_name = %s,
                            translation_source = 'ai',
                            translation_date = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE
                            (LOWER(REPLACE(english_name, ' ', '')) = LOWER(REPLACE(%s, ' ', ''))
                            OR LOWER(REPLACE(japanese_name, ' ', '')) = LOWER(REPLACE(%s, ' ', '')))
                            AND is_qoo10_official = TRUE
                    """

                    cur.execute(query, (
                        korean_brand,
                        pd.to_datetime(row['created_date']).date(),
                        english_brand,
                        japanese_brand
                    ))

                    if cur.rowcount > 0:
                        updated_count += cur.rowcount
                    else:
                        not_matched_count += 1
                        not_matched_brands.append({
                            'korean': korean_brand,
                            'english': english_brand,
                            'japanese': japanese_brand
                        })

            self.stats['korean_names_added'] = updated_count
            logger.info(f"✓ {updated_count}개 브랜드에 한국어 이름 추가 완료")

            if not_matched_count > 0:
                logger.warning(f"⚠️  매칭 실패: {not_matched_count}개 (Qoo10에 없는 브랜드)")
                logger.warning(f"   전체 목록:")
                for i, brand in enumerate(not_matched_brands, 1):
                    logger.warning(f"   {i}. {brand['korean']} (영어: {brand['english']}, 일본어: {brand['japanese']})")

        except Exception as e:
            logger.error(f"✗ 브랜드 번역 마이그레이션 실패: {e}")
            self.stats['errors'] += 1
            raise

    def migrate_categories(self, file_path: Path) -> None:
        """
        Qoo10_CategoryInfo.csv에서 카테고리 로드

        Args:
            file_path: Qoo10_CategoryInfo.csv 파일 경로
        """
        logger.info(f"=== 카테고리 마이그레이션 시작: {file_path} ===")

        try:
            # BOM 인코딩 처리
            df = pd.read_csv(file_path, encoding='utf-8-sig')
            logger.info(f"총 {len(df)}개 카테고리 로드")

            if self.dry_run:
                logger.info(f"[DRY RUN] 샘플 데이터:\n{df.head()}")
                return

            # INSERT 쿼리 (ON CONFLICT DO NOTHING)
            query = """
                INSERT INTO categories (
                    category_code, large_code, large_name,
                    medium_code, medium_name, small_name, created_at
                )
                VALUES %s
                ON CONFLICT (category_code) DO NOTHING
            """

            # 소카테고리 코드를 category_code로 사용 (9자리)
            values = [
                (
                    str(row['소카테고리 코드']),
                    str(row['대카테고리 코드']),
                    row['대카테고리 명'],
                    str(row['중카테고리 코드']),
                    row['중카테고리 명'],
                    row['소카테고리 명'],
                    datetime.now()
                )
                for _, row in df.iterrows()
            ]

            with self.conn.cursor() as cur:
                execute_values(cur, query, values)
                self.stats['categories_inserted'] += len(values)

            logger.info(f"✓ {len(values)}개 카테고리 저장 완료")

        except Exception as e:
            logger.error(f"✗ 카테고리 마이그레이션 실패: {e}")
            self.stats['errors'] += 1
            raise

    def print_stats(self) -> None:
        """마이그레이션 통계 출력"""
        logger.info("\n" + "="*50)
        logger.info("마이그레이션 통계")
        logger.info("="*50)
        logger.info(f"1. Qoo10 브랜드 삽입: {self.stats['qoo10_brands_inserted']}개")
        logger.info(f"2. 한국어 이름 추가: {self.stats['korean_names_added']}개")
        logger.info(f"3. 금지 브랜드 처리: {self.stats['brands_banned']}개")
        logger.info(f"   - Qoo10에 없는 금지 브랜드: {self.stats['ban_not_in_qoo10']}개 (로그만)")
        logger.info(f"4. 카테고리 삽입: {self.stats['categories_inserted']}개")
        logger.info(f"에러 발생: {self.stats['errors']}건")
        logger.info("="*50)


def main():
    parser = argparse.ArgumentParser(description='초기 데이터 마이그레이션')
    parser.add_argument(
        '--db-url',
        default='postgresql://postgres:password@localhost:5432/asmama',
        help='PostgreSQL 연결 URL'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='실제 DB에 쓰지 않고 테스트만 실행'
    )
    parser.add_argument(
        '--skip-brands',
        action='store_true',
        help='브랜드 마이그레이션 건너뛰기'
    )
    parser.add_argument(
        '--skip-categories',
        action='store_true',
        help='카테고리 마이그레이션 건너뛰기'
    )

    args = parser.parse_args()

    # 파일 경로 설정
    base_dir = Path(__file__).parent.parent
    ban_file = base_dir / 'uploader/templates/ban/ban.xlsx'
    brand_file = base_dir / 'uploader/templates/brand/brand.csv'
    translation_file = base_dir / 'uploader/templates/translation/brand_translations.csv'
    category_file = base_dir / 'uploader/templates/category/Qoo10_CategoryInfo.csv'

    # 파일 존재 확인
    for file_path in [ban_file, brand_file, translation_file, category_file]:
        if not file_path.exists():
            logger.error(f"파일을 찾을 수 없습니다: {file_path}")
            sys.exit(1)

    try:
        with DataMigrator(args.db_url, args.dry_run) as migrator:
            if args.dry_run:
                logger.warning("⚠️  DRY RUN 모드: 실제 DB에 쓰지 않습니다")

            # 브랜드 마이그레이션 (순서 중요!)
            if not args.skip_brands:
                # 1. Qoo10 공식 브랜드 먼저 삽입 (brand_no, 영어/일본어 이름)
                migrator.migrate_qoo10_brands(brand_file)

                # 2. 번역 데이터로 한국어 이름 추가
                migrator.migrate_brand_translations(translation_file)

                # 3. 금지 브랜드 처리 (Qoo10에 있는 것만)
                migrator.migrate_ban_brands(ban_file)

            # 카테고리 마이그레이션
            if not args.skip_categories:
                migrator.migrate_categories(category_file)

            migrator.print_stats()

            if not args.dry_run:
                logger.info("✓ 마이그레이션 완료!")

    except Exception as e:
        logger.error(f"✗ 마이그레이션 실패: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

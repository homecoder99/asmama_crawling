"""
Qoo10_ItemInfo Excel 파일의 데이터를 upload_history 테이블로 이전하는 스크립트.

사용법:
    python scripts/migrate_qoo10_to_upload_history.py --input data/Qoo10_ItemInfo_20251021171235.xlsx --user admin
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime
import pandas as pd
import psycopg2
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_to_upload_history(excel_file: str, uploaded_by: str = "admin", skip_rows: int = 2):
    """
    Qoo10_ItemInfo Excel 파일의 seller_unique_item_id를 upload_history로 이전한다.

    Args:
        excel_file: Qoo10_ItemInfo Excel 파일 경로
        uploaded_by: 업로드한 유저 식별자 (기본값: admin)
        skip_rows: 스킵할 행 수 (기본값: 2, 헤더 제외)

    Returns:
        성공 여부
    """
    try:
        # 1. Excel 파일 로드
        logger.info(f"📂 Excel 파일 로딩: {excel_file}")
        df = pd.read_excel(excel_file, skiprows=skip_rows)

        if 'seller_unique_item_id' not in df.columns:
            logger.error("❌ 'seller_unique_item_id' 컬럼이 없습니다.")
            return False

        # NaN 제거 및 중복 제거
        unique_item_ids = df['seller_unique_item_id'].dropna().unique()
        logger.info(f"✅ 고유 상품 ID: {len(unique_item_ids)}개")

        # 2. DB 연결
        connection_string = os.getenv("DATABASE_URL")
        if not connection_string:
            logger.error("❌ DATABASE_URL 환경변수가 설정되지 않았습니다.")
            return False

        conn = psycopg2.connect(connection_string)
        cursor = conn.cursor()

        # 3. crawled_products에서 unique_item_id 기준으로 id 조회
        logger.info(f"🔍 crawled_products에서 매칭 조회 중...")

        matched_count = 0
        not_found_count = 0
        already_exists_count = 0
        inserted_count = 0

        for unique_item_id in unique_item_ids:
            unique_item_id_str = str(unique_item_id).strip()
            if not unique_item_id_str:
                continue

            # crawled_products에서 조회
            cursor.execute("""
                SELECT id FROM crawled_products
                WHERE unique_item_id = %s
                LIMIT 1
            """, (unique_item_id_str,))

            result = cursor.fetchone()

            if result:
                crawled_product_id = result[0]
                matched_count += 1

                # upload_history에 이미 있는지 확인
                cursor.execute("""
                    SELECT COUNT(*) FROM upload_history
                    WHERE crawled_product_id = %s AND uploaded_by = %s
                """, (crawled_product_id, uploaded_by))

                if cursor.fetchone()[0] > 0:
                    already_exists_count += 1
                    logger.debug(f"⏭️  이미 존재: {unique_item_id_str}")
                    continue

                # upload_history에 INSERT
                cursor.execute("""
                    INSERT INTO upload_history (crawled_product_id, uploaded_by, uploaded_at)
                    VALUES (%s, %s, NOW())
                """, (crawled_product_id, uploaded_by))

                inserted_count += 1

                if inserted_count % 100 == 0:
                    logger.info(f"✅ 진행중: {inserted_count}개 추가...")

            else:
                not_found_count += 1
                logger.debug(f"❓ crawled_products에 없음: {unique_item_id_str}")

        # 4. 커밋
        conn.commit()

        # 5. 결과 출력
        logger.info("\n" + "=" * 60)
        logger.info("📊 이전 결과:")
        logger.info(f"  Excel 고유 상품 ID: {len(unique_item_ids)}개")
        logger.info(f"  crawled_products 매칭: {matched_count}개")
        logger.info(f"  이미 존재하는 이력: {already_exists_count}개")
        logger.info(f"  신규 추가: {inserted_count}개")
        logger.info(f"  매칭 실패: {not_found_count}개")
        logger.info("=" * 60)

        cursor.close()
        conn.close()

        if inserted_count > 0:
            logger.info(f"✅ upload_history에 {inserted_count}개 이력 추가 완료")
        else:
            logger.warning("⚠️  추가된 이력이 없습니다.")

        return True

    except Exception as e:
        logger.error(f"❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Qoo10_ItemInfo Excel 파일을 upload_history 테이블로 이전"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Qoo10_ItemInfo Excel 파일 경로"
    )
    parser.add_argument(
        "--user",
        default="admin",
        help="업로드 유저 식별자 (기본값: admin)"
    )
    parser.add_argument(
        "--skip-rows",
        type=int,
        default=2,
        help="스킵할 행 수 (기본값: 2)"
    )

    args = parser.parse_args()

    # 파일 존재 확인
    if not Path(args.input).exists():
        logger.error(f"❌ 파일이 존재하지 않습니다: {args.input}")
        sys.exit(1)

    # 이전 실행
    success = migrate_to_upload_history(
        excel_file=args.input,
        uploaded_by=args.user,
        skip_rows=args.skip_rows
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
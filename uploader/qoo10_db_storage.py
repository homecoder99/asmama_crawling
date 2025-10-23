"""qoo10_products 테이블용 PostgreSQL 저장소 구현."""

from typing import Any, Dict, List, Union, Optional
import logging
import os
from datetime import datetime

try:
    import psycopg2
    from psycopg2.extras import execute_values
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


class Qoo10ProductsStorage:
    """
    qoo10_products 테이블용 PostgreSQL 저장소.

    업로드용으로 변환된 제품 데이터를 qoo10_products 테이블에 저장한다.
    """

    def __init__(self, connection_string: Optional[str] = None, table_name: str = "qoo10_products"):
        """
        Qoo10ProductsStorage 초기화.

        Args:
            connection_string: PostgreSQL 연결 문자열 (기본값: DATABASE_URL 환경변수)
            table_name: 데이터를 저장할 테이블명 (기본값: qoo10_products)
        """
        self.logger = logging.getLogger(__name__)

        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2가 설치되지 않았습니다. pip install psycopg2-binary를 실행하세요.")

        # 연결 문자열 설정
        self.connection_string = connection_string or os.getenv("DATABASE_URL")
        if not self.connection_string:
            raise ValueError("DATABASE_URL 환경변수가 설정되지 않았습니다.")

        self.table_name = table_name
        self.conn = None

        # 연결 테스트
        self._connect()

    def _connect(self):
        """데이터베이스에 연결한다."""
        try:
            if self.conn is None or self.conn.closed:
                self.conn = psycopg2.connect(self.connection_string)
                self.logger.info(f"PostgreSQL 연결 성공: {self.table_name}")
        except Exception as e:
            self.logger.error(f"PostgreSQL 연결 실패: {str(e)}")
            raise

    def _ensure_connection(self):
        """연결이 유효한지 확인하고 필요시 재연결한다."""
        try:
            if self.conn is None or self.conn.closed:
                self._connect()
        except Exception as e:
            self.logger.error(f"연결 확인 실패: {str(e)}")
            raise

    def save(self, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> bool:
        """
        데이터를 qoo10_products 테이블에 저장한다.

        Args:
            data: 저장할 데이터 (단일 또는 리스트)

        Returns:
            저장 성공 여부
        """
        try:
            self._ensure_connection()

            # 단일 데이터를 리스트로 변환
            if isinstance(data, dict):
                data = [data]

            if not data:
                self.logger.warning("저장할 데이터가 없습니다.")
                return True

            # INSERT 쿼리 실행
            with self.conn.cursor() as cursor:
                # UPSERT 쿼리 (seller_unique_item_id 기준 중복 체크)
                insert_query = f"""
                    INSERT INTO {self.table_name} (
                        seller_unique_item_id, category_number, brand_number, item_name,
                        price_yen, image_main_url, item_description,
                        item_name_ja, item_name_en, item_name_zh, search_keywords,
                        model_name, manufacturer, origin_country, material, color,
                        size, weight, volume, age_group, gender, season,
                        expiry_date, manufacture_date, certification_info, caution_info,
                        storage_method, usage_method, ingredients, nutritional_info,
                        warranty_info, as_info, shipping_method, shipping_fee,
                        return_shipping_fee, exchange_info, refund_info,
                        available_coupon, available_point, tax_type,
                        additional_images, detail_images, option_type, option_info,
                        stock_quantity, min_order_quantity, max_order_quantity,
                        source_crawled_product_id, created_at, updated_at
                    ) VALUES %s
                    ON CONFLICT (seller_unique_item_id) DO UPDATE SET
                        item_name = EXCLUDED.item_name,
                        price_yen = EXCLUDED.price_yen,
                        image_main_url = EXCLUDED.image_main_url,
                        item_description = EXCLUDED.item_description,
                        option_info = EXCLUDED.option_info,
                        stock_quantity = EXCLUDED.stock_quantity,
                        updated_at = EXCLUDED.updated_at
                """

                # 값 준비
                now = datetime.now()
                values = []

                for item in data:
                    # Helper function: 빈 문자열을 NULL로 변환
                    def nullable(value, default=''):
                        if value == '' or value is None:
                            return None if default == '' else default
                        return value

                    values.append((
                        item.get('seller_unique_item_id', ''),
                        nullable(item.get('category_number')),
                        nullable(item.get('brand_number')),
                        item.get('item_name', ''),
                        item.get('price_yen') or 0,
                        item.get('image_main_url', ''),
                        item.get('item_description', ''),
                        item.get('item_name_ja', ''),
                        item.get('item_name_en', ''),
                        item.get('item_name_zh', ''),
                        item.get('search_keywords', ''),
                        item.get('model_name', ''),
                        item.get('manufacturer', ''),
                        item.get('origin_country', ''),
                        item.get('material', ''),
                        item.get('color', ''),
                        item.get('size', ''),
                        item.get('weight', ''),
                        item.get('volume', ''),
                        item.get('age_group', ''),
                        item.get('gender', ''),
                        item.get('season', ''),
                        nullable(item.get('expiry_date')),
                        nullable(item.get('manufacture_date')),
                        item.get('certification_info', ''),
                        item.get('caution_info', ''),
                        item.get('storage_method', ''),
                        item.get('usage_method', ''),
                        item.get('ingredients', ''),
                        item.get('nutritional_info', ''),
                        item.get('warranty_info', ''),
                        item.get('as_info', ''),
                        item.get('shipping_method', ''),
                        nullable(item.get('shipping_fee')),
                        nullable(item.get('return_shipping_fee')),
                        item.get('exchange_info', ''),
                        item.get('refund_info', ''),
                        nullable(item.get('available_coupon')),
                        nullable(item.get('available_point')),
                        item.get('tax_type', ''),
                        item.get('additional_images', ''),
                        item.get('detail_images', ''),
                        item.get('option_type', ''),
                        item.get('option_info', ''),
                        nullable(item.get('stock_quantity'), 0),
                        nullable(item.get('min_order_quantity'), 1),
                        nullable(item.get('max_order_quantity')),
                        item.get('source_crawled_product_id'),
                        now,
                        now
                    ))

                execute_values(cursor, insert_query, values)
                self.conn.commit()

            self.logger.info(f"qoo10_products 저장 완료: {len(data)}개 항목")
            return True

        except Exception as e:
            self.logger.error(f"qoo10_products 저장 실패: {str(e)}")
            if self.conn:
                self.conn.rollback()
            return False

    def close(self):
        """데이터베이스 연결을 닫는다."""
        if self.conn and not self.conn.closed:
            self.conn.close()
            self.logger.info("PostgreSQL 연결 종료")

    def __del__(self):
        """소멸자에서 연결을 닫는다."""
        self.close()

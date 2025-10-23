"""PostgreSQL 데이터베이스 저장소 구현."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Union, Optional
import logging
import os
from datetime import datetime
import json

try:
    import psycopg2
    from psycopg2.extras import execute_values, RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

from .storage import BaseStorage


class PostgresStorage(BaseStorage):
    """
    PostgreSQL 데이터베이스 기반 데이터 저장소.

    crawled_products 테이블에 크롤링 데이터를 저장한다.
    """

    def __init__(self, connection_string: Optional[str] = None, table_name: str = "crawled_products"):
        """
        PostgreSQL 저장소를 초기화한다.

        Args:
            connection_string: PostgreSQL 연결 문자열 (기본값: DATABASE_URL 환경변수)
            table_name: 데이터를 저장할 테이블명 (기본값: crawled_products)
        """
        from .utils import setup_logger
        self.logger = setup_logger(self.__class__.__name__)

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
        데이터를 PostgreSQL에 저장한다.

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

            # 데이터 변환: 크롤러 형식 → DB 형식
            transformed_data = [self._transform_to_db_schema(item) for item in data]

            # INSERT 쿼리 실행
            with self.conn.cursor() as cursor:
                # UPSERT 쿼리 (unique_item_id 기준 중복 체크)
                insert_query = f"""
                    INSERT INTO {self.table_name} (
                        goods_no, item_name, price, origin_price, is_discounted,
                        discount_info, discount_start_date, discount_end_date,
                        brand_name, manufacturer, origin_country,
                        category_main, category_sub, category_detail,
                        category_main_id, category_sub_id, category_detail_id,
                        category_name, images, is_option_available, option_info,
                        benefit_info, shipping_info, refund_info, is_soldout,
                        others, unique_item_id, source, origin_product_url,
                        crawled_at, created_at, updated_at
                    ) VALUES %s
                    ON CONFLICT (unique_item_id) DO UPDATE SET
                        item_name = EXCLUDED.item_name,
                        price = EXCLUDED.price,
                        origin_price = EXCLUDED.origin_price,
                        is_discounted = EXCLUDED.is_discounted,
                        discount_info = EXCLUDED.discount_info,
                        images = EXCLUDED.images,
                        option_info = EXCLUDED.option_info,
                        is_soldout = EXCLUDED.is_soldout,
                        crawled_at = EXCLUDED.crawled_at,
                        updated_at = EXCLUDED.updated_at
                """

                values = [
                    (
                        item['goods_no'], item['item_name'], item['price'], item['origin_price'],
                        item['is_discounted'], item['discount_info'], item['discount_start_date'],
                        item['discount_end_date'], item['brand_name'], item['manufacturer'],
                        item['origin_country'], item['category_main'], item['category_sub'],
                        item['category_detail'], item['category_main_id'], item['category_sub_id'],
                        item['category_detail_id'], item['category_name'], item['images'],
                        item['is_option_available'], item['option_info'], item['benefit_info'],
                        item['shipping_info'], item['refund_info'], item['is_soldout'],
                        item['others'], item['unique_item_id'], item['source'],
                        item['origin_product_url'], item['crawled_at'], item['created_at'],
                        item['updated_at']
                    )
                    for item in transformed_data
                ]

                execute_values(cursor, insert_query, values)
                self.conn.commit()

            self.logger.info(f"PostgreSQL 저장 완료: {len(data)}개 항목")
            return True

        except Exception as e:
            self.logger.error(f"PostgreSQL 저장 실패: {str(e)}")
            if self.conn:
                self.conn.rollback()
            return False

    def _transform_to_db_schema(self, crawler_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        크롤러 데이터를 DB 스키마로 변환한다.

        크롤러 스키마 (엑셀):
            - branduid (goods_no)
            - name (item_name)
            - price
            - options (list -> JSON string)
            - image_urls (list -> $$ separated string)
            - detail_html

        DB 스키마:
            - goods_no, item_name, price, origin_price, is_discounted
            - discount_info, discount_start_date, discount_end_date
            - brand_name, manufacturer, origin_country
            - category_main, category_sub, category_detail
            - category_main_id, category_sub_id, category_detail_id
            - category_name, images, is_option_available, option_info
            - benefit_info, shipping_info, refund_info, is_soldout
            - others, unique_item_id, source, origin_product_url
            - crawled_at, created_at, updated_at

        Args:
            crawler_data: 크롤러에서 수집한 원본 데이터

        Returns:
            DB 스키마로 변환된 데이터
        """
        now = datetime.now()

        # 기본 매핑
        db_data = {
            'goods_no': crawler_data.get('goods_no', crawler_data.get('branduid', '')),
            'item_name': crawler_data.get('item_name', crawler_data.get('name', '')),
            'price': crawler_data.get('price', 0),
            'origin_price': crawler_data.get('origin_price', crawler_data.get('price', 0)),
            'is_discounted': crawler_data.get('is_discounted', False),
            'discount_info': crawler_data.get('discount_info', ''),
            'discount_start_date': crawler_data.get('discount_start_date'),
            'discount_end_date': crawler_data.get('discount_end_date'),
            'brand_name': crawler_data.get('brand_name', ''),
            'manufacturer': crawler_data.get('manufacturer', ''),
            'origin_country': crawler_data.get('origin_country', ''),
            'category_main': crawler_data.get('category_main', ''),
            'category_sub': crawler_data.get('category_sub', ''),
            'category_detail': crawler_data.get('category_detail', ''),
            'category_main_id': crawler_data.get('category_main_id'),
            'category_sub_id': crawler_data.get('category_sub_id'),
            'category_detail_id': crawler_data.get('category_detail_id'),
            'category_name': crawler_data.get('category_name', ''),
            'is_option_available': crawler_data.get('is_option_available', False),
            'benefit_info': crawler_data.get('benefit_info', ''),
            'shipping_info': crawler_data.get('shipping_info', ''),
            'refund_info': crawler_data.get('refund_info', ''),
            'is_soldout': crawler_data.get('is_soldout', False),
            'others': crawler_data.get('others', ''),
            'source': crawler_data.get('source', 'oliveyoung'),
            'origin_product_url': crawler_data.get('origin_product_url', ''),
            'crawled_at': now,
            'created_at': now,
            'updated_at': now
        }

        # unique_item_id 생성
        db_data['unique_item_id'] = f"{db_data['source']}_{db_data['goods_no']}"

        # images: list -> $$ separated string
        # 크롤러는 'images' 또는 'image_urls' 키를 사용할 수 있음
        image_urls = crawler_data.get('images', crawler_data.get('image_urls', []))
        if isinstance(image_urls, list):
            db_data['images'] = '$$'.join(image_urls)
        elif isinstance(image_urls, str):
            db_data['images'] = image_urls
        else:
            db_data['images'] = ''

        # option_info: list -> custom format
        options = crawler_data.get('options', [])
        if isinstance(options, list) and options:
            option_lines = []
            for idx, opt in enumerate(options, 1):
                if isinstance(opt, dict):
                    name = opt.get('name', '')
                    price = opt.get('additional_price', 0)
                    stock = opt.get('stock', 200)
                    unique_id = f"{db_data['unique_item_id']}_{idx}"
                    option_lines.append(f"Option{idx}||*{name} {price}원||*{price}||*{stock}||*{unique_id}")
                elif isinstance(opt, str):
                    option_lines.append(f"Option{idx}||*{opt}||*0||*200||*{db_data['unique_item_id']}_{idx}")
            db_data['option_info'] = '$$'.join(option_lines)
        elif isinstance(options, str):
            db_data['option_info'] = options
        else:
            db_data['option_info'] = ''

        return db_data

    def load(self) -> List[Dict[str, Any]]:
        """
        PostgreSQL에서 데이터를 로드한다.

        Returns:
            로드된 데이터 목록
        """
        try:
            self._ensure_connection()

            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(f"SELECT * FROM {self.table_name} ORDER BY created_at DESC")
                rows = cursor.fetchall()

                # RealDictRow를 일반 dict로 변환
                return [dict(row) for row in rows]

        except Exception as e:
            self.logger.error(f"PostgreSQL 데이터 로드 실패: {str(e)}")
            return []

    def clear(self) -> bool:
        """
        테이블의 모든 데이터를 삭제한다.

        주의: 이 작업은 되돌릴 수 없습니다!

        Returns:
            삭제 성공 여부
        """
        try:
            self._ensure_connection()

            with self.conn.cursor() as cursor:
                cursor.execute(f"DELETE FROM {self.table_name}")
                self.conn.commit()

            self.logger.info(f"테이블 초기화 완료: {self.table_name}")
            return True

        except Exception as e:
            self.logger.error(f"테이블 초기화 실패: {str(e)}")
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

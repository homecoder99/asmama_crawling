"""데이터 소스 어댑터 패턴 구현.

엑셀과 PostgreSQL 등 다양한 데이터 소스를 통일된 인터페이스로 변환한다.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import pandas as pd
import logging
import os
import json

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


class DataAdapter(ABC):
    """
    데이터 소스 어댑터의 추상 베이스 클래스.

    다양한 데이터 소스(엑셀, DB 등)를 통일된 DataFrame 형식으로 변환한다.
    """

    @abstractmethod
    def load_products(self) -> pd.DataFrame:
        """
        제품 데이터를 통일된 DataFrame 형식으로 로드한다.

        Returns:
            통일된 스키마의 DataFrame
        """
        pass

    @abstractmethod
    def get_source_type(self) -> str:
        """
        데이터 소스 타입을 반환한다.

        Returns:
            소스 타입 ('excel', 'postgres', 등)
        """
        pass


class ExcelDataAdapter(DataAdapter):
    """
    엑셀 파일 데이터 어댑터.

    기존 엑셀 크롤링 데이터를 로드한다.
    """

    def __init__(self, file_path: str):
        """
        엑셀 어댑터를 초기화한다.

        Args:
            file_path: 엑셀 파일 경로
        """
        self.file_path = file_path
        self.logger = logging.getLogger(__name__)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"엑셀 파일을 찾을 수 없습니다: {file_path}")

    def load_products(self) -> pd.DataFrame:
        """
        엑셀 파일에서 제품 데이터를 로드한다.

        엑셀 스키마:
            - branduid (goods_no)
            - name (item_name)
            - price
            - options (JSON string)
            - image_urls (JSON string)
            - detail_html
            - 기타 필드들...

        Returns:
            통일된 스키마의 DataFrame
        """
        try:
            self.logger.info(f"엑셀 파일 로딩 중: {self.file_path}")

            # 엑셀 파일 읽기
            df = pd.read_excel(self.file_path)

            # 데이터 소스 자동 감지 (Asmama vs Oliveyoung)
            if 'branduid' in df.columns and 'name' in df.columns:
                # Asmama 스키마
                self.logger.info("Asmama 스키마 감지")
                source_type = 'asmama'
            elif 'goods_no' in df.columns and 'item_name' in df.columns:
                # Oliveyoung 스키마
                self.logger.info("Oliveyoung 스키마 감지")
                source_type = 'oliveyoung'
                # Oliveyoung 컬럼을 통일된 형식으로 매핑
                df['branduid'] = df['goods_no']
                df['name'] = df['item_name']
            else:
                raise ValueError(f"알 수 없는 스키마: 필수 컬럼 없음 (branduid/name 또는 goods_no/item_name)")

            # JSON 문자열을 Python 객체로 변환
            if 'image_urls' in df.columns:
                df['image_urls'] = df['image_urls'].apply(
                    lambda x: json.loads(x) if isinstance(x, str) and x.startswith('[') else x
                )

            if 'options' in df.columns:
                df['options'] = df['options'].apply(
                    lambda x: json.loads(x) if isinstance(x, str) and x.startswith('[') else x
                )

            self.logger.info(f"엑셀 파일 로딩 완료: {len(df)}개 항목")
            return df

        except Exception as e:
            self.logger.error(f"엑셀 파일 로딩 실패: {str(e)}")
            raise

    def get_source_type(self) -> str:
        """소스 타입 반환."""
        return "excel"


class PostgresDataAdapter(DataAdapter):
    """
    PostgreSQL 데이터베이스 어댑터.

    DB의 crawled_products 테이블에서 데이터를 로드하고
    엑셀과 동일한 스키마로 변환한다.
    """

    def __init__(self, connection_string: Optional[str] = None, table_name: str = "crawled_products",
                 source_filter: Optional[str] = "oliveyoung"):
        """
        PostgreSQL 어댑터를 초기화한다.

        Args:
            connection_string: PostgreSQL 연결 문자열 (기본값: DATABASE_URL 환경변수)
            table_name: 데이터를 읽을 테이블명 (기본값: crawled_products)
            source_filter: 소스 필터링 (기본값: oliveyoung)
        """
        self.logger = logging.getLogger(__name__)

        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2가 설치되지 않았습니다. pip install psycopg2-binary를 실행하세요.")

        self.connection_string = connection_string or os.getenv("DATABASE_URL")
        if not self.connection_string:
            raise ValueError("DATABASE_URL 환경변수가 설정되지 않았습니다.")

        self.table_name = table_name
        self.source_filter = source_filter
        self.conn = None

    def _connect(self):
        """데이터베이스에 연결한다."""
        try:
            if self.conn is None or self.conn.closed:
                self.conn = psycopg2.connect(self.connection_string)
                self.logger.info(f"PostgreSQL 연결 성공: {self.table_name}")
        except Exception as e:
            self.logger.error(f"PostgreSQL 연결 실패: {str(e)}")
            raise

    def load_products(self) -> pd.DataFrame:
        """
        PostgreSQL에서 제품 데이터를 로드하고 엑셀 스키마로 변환한다.

        DB 스키마 → 엑셀 스키마 변환:
            - goods_no → branduid
            - item_name → name
            - images ($$ separated) → image_urls (list)
            - option_info (custom format) → options (list)

        Returns:
            엑셀과 동일한 스키마의 DataFrame
        """
        try:
            self._connect()

            self.logger.info(f"PostgreSQL에서 데이터 로딩 중: {self.table_name}")

            # 쿼리 실행
            query = f"SELECT * FROM {self.table_name}"
            if self.source_filter:
                query += f" WHERE source = '{self.source_filter}'"
            query += " ORDER BY created_at DESC"

            df = pd.read_sql_query(query, self.conn)

            if df.empty:
                self.logger.warning("로드된 데이터가 없습니다.")
                return df

            # DB 스키마 → 엑셀 스키마 변환
            df_transformed = self._transform_to_excel_schema(df)

            self.logger.info(f"PostgreSQL 데이터 로딩 완료: {len(df_transformed)}개 항목")
            return df_transformed

        except Exception as e:
            self.logger.error(f"PostgreSQL 데이터 로딩 실패: {str(e)}")
            raise
        finally:
            if self.conn and not self.conn.closed:
                self.conn.close()

    def _transform_to_excel_schema(self, db_df: pd.DataFrame) -> pd.DataFrame:
        """
        DB 스키마를 엑셀 스키마로 변환한다.

        Args:
            db_df: DB에서 로드한 DataFrame

        Returns:
            엑셀 스키마로 변환된 DataFrame
        """
        # 기본 컬럼 매핑
        column_mapping = {
            'goods_no': 'branduid',
            'item_name': 'name'
        }

        # 컬럼명 변경
        df = db_df.rename(columns=column_mapping)

        # images: DB의 $$ separated string을 그대로 유지 (Excel 스키마와 동일)
        # uploader는 images 필드를 문자열로 기대함

        # option_info: custom format → list
        if 'option_info' in df.columns:
            df['options'] = df['option_info'].apply(self._parse_option_info)

        # detail_html 생성 (DB에는 없으므로 빈 문자열)
        if 'detail_html' not in df.columns:
            df['detail_html'] = ''

        # 필요한 컬럼만 선택 (엑셀 스키마와 동일하게)
        excel_columns = ['branduid', 'name', 'price', 'options', 'images']

        # DB의 추가 컬럼들도 포함 (uploader에서 사용할 수 있도록)
        additional_columns = [
            'origin_price', 'is_discounted', 'discount_info', 'discount_start_date', 'discount_end_date',
            'brand_name', 'manufacturer', 'origin_country',
            'category_main', 'category_sub', 'category_detail',
            'category_main_id', 'category_sub_id', 'category_detail_id',
            'category_name', 'is_option_available',
            'benefit_info', 'shipping_info', 'refund_info', 'is_soldout',
            'others', 'unique_item_id', 'source', 'origin_product_url',
            'detail_html'
        ]

        # 존재하는 컬럼만 선택
        final_columns = excel_columns + [col for col in additional_columns if col in df.columns]
        existing_columns = [col for col in final_columns if col in df.columns]

        return df[existing_columns]

    def _parse_option_info(self, option_info_str: str) -> List[Dict[str, Any]]:
        """
        option_info 문자열을 파싱하여 options 리스트로 변환한다.

        형식: Option1||*name price||*additional_price||*stock||*unique_id$$Option2||*...

        Args:
            option_info_str: option_info 문자열

        Returns:
            options 리스트
        """
        if not option_info_str or not isinstance(option_info_str, str):
            return []

        options = []
        try:
            # $$ 구분자로 분할
            option_lines = option_info_str.split('$$')

            for line in option_lines:
                if not line.strip():
                    continue

                # ||* 구분자로 분할
                parts = [p.strip() for p in line.split('||*')]

                if len(parts) >= 4:
                    # parts[0]: Option1
                    # parts[1]: name price
                    # parts[2]: additional_price
                    # parts[3]: stock
                    # parts[4]: unique_id (optional)

                    name = parts[1].split(' ')[0] if ' ' in parts[1] else parts[1]

                    try:
                        additional_price = int(parts[2])
                    except (ValueError, IndexError):
                        additional_price = 0

                    try:
                        stock = int(parts[3])
                    except (ValueError, IndexError):
                        stock = 200

                    options.append({
                        'name': name,
                        'additional_price': additional_price,
                        'stock': stock
                    })

        except Exception as e:
            self.logger.warning(f"옵션 정보 파싱 실패: {str(e)}")
            return []

        return options

    def get_source_type(self) -> str:
        """소스 타입 반환."""
        return "postgres"


class DataAdapterFactory:
    """
    데이터 어댑터 팩토리.

    소스 타입에 따라 적절한 어댑터를 생성한다.
    """

    @staticmethod
    def create_adapter(source_type: str, **kwargs) -> DataAdapter:
        """
        소스 타입에 맞는 어댑터를 생성한다.

        Args:
            source_type: 데이터 소스 타입 ('excel', 'postgres')
            **kwargs: 어댑터별 초기화 인자

        Returns:
            DataAdapter 인스턴스

        Raises:
            ValueError: 지원하지 않는 소스 타입
        """
        if source_type == "excel":
            file_path = kwargs.get('file_path')
            if not file_path:
                raise ValueError("엑셀 어댑터는 file_path가 필요합니다.")
            return ExcelDataAdapter(file_path=file_path)

        elif source_type == "postgres":
            return PostgresDataAdapter(
                connection_string=kwargs.get('connection_string'),
                table_name=kwargs.get('table_name', 'crawled_products'),
                source_filter=kwargs.get('source_filter', 'oliveyoung')
            )

        else:
            raise ValueError(f"지원하지 않는 소스 타입입니다: {source_type}")

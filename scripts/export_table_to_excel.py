"""PostgreSQL 테이블을 엑셀 파일로 내보내는 범용 스크립트.

모든 테이블과 호환되며, 다양한 내보내기 옵션을 제공한다.
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List

import psycopg2
import pandas as pd
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PostgresTableExporter:
    """
    PostgreSQL 테이블을 엑셀 파일로 내보내는 클래스.
    """

    def __init__(self, db_url: Optional[str] = None):
        """
        Exporter 초기화.

        Args:
            db_url: PostgreSQL 연결 URL (기본값: 환경변수 DATABASE_URL)
        """
        self.db_url = db_url or os.getenv('DATABASE_URL')
        if not self.db_url:
            raise ValueError("DATABASE_URL이 설정되지 않았습니다. 환경변수 또는 인자로 전달하세요.")

        self.conn = None
        self.logger = logger

    def connect(self) -> bool:
        """
        데이터베이스에 연결한다.

        Returns:
            연결 성공 여부
        """
        try:
            self.conn = psycopg2.connect(self.db_url)
            self.logger.info("PostgreSQL 연결 성공")
            return True
        except Exception as e:
            self.logger.error(f"PostgreSQL 연결 실패: {str(e)}")
            return False

    def disconnect(self):
        """데이터베이스 연결을 종료한다."""
        if self.conn:
            self.conn.close()
            self.logger.info("PostgreSQL 연결 종료")

    def list_tables(self, schema: str = 'public') -> List[str]:
        """
        스키마의 모든 테이블 목록을 가져온다.

        Args:
            schema: 스키마 이름 (기본값: public)

        Returns:
            테이블 이름 목록
        """
        try:
            query = """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                AND table_type = 'BASE TABLE'
                ORDER BY table_name;
            """
            df = pd.read_sql_query(query, self.conn, params=(schema,))
            tables = df['table_name'].tolist()
            self.logger.info(f"스키마 '{schema}'에서 {len(tables)}개 테이블 발견")
            return tables
        except Exception as e:
            self.logger.error(f"테이블 목록 조회 실패: {str(e)}")
            return []

    def get_table_info(self, table_name: str, schema: str = 'public') -> dict:
        """
        테이블의 메타데이터를 가져온다.

        Args:
            table_name: 테이블 이름
            schema: 스키마 이름

        Returns:
            테이블 정보 (행 수, 컬럼 수, 컬럼 목록)
        """
        try:
            # 행 수 조회
            count_query = f'SELECT COUNT(*) FROM "{schema}"."{table_name}"'
            row_count = pd.read_sql_query(count_query, self.conn).iloc[0, 0]

            # 컬럼 정보 조회
            column_query = """
                SELECT column_name, data_type, character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position;
            """
            columns_df = pd.read_sql_query(column_query, self.conn, params=(schema, table_name))

            return {
                'table_name': table_name,
                'row_count': row_count,
                'column_count': len(columns_df),
                'columns': columns_df['column_name'].tolist(),
                'column_types': columns_df['data_type'].tolist()
            }
        except Exception as e:
            self.logger.error(f"테이블 정보 조회 실패: {str(e)}")
            return {}

    def export_table(
        self,
        table_name: str,
        output_file: str,
        schema: str = 'public',
        limit: Optional[int] = None,
        where_clause: Optional[str] = None,
        columns: Optional[List[str]] = None
    ) -> bool:
        """
        테이블을 엑셀 파일로 내보낸다.

        Args:
            table_name: 테이블 이름
            output_file: 출력 파일 경로
            schema: 스키마 이름 (기본값: public)
            limit: 최대 행 수 제한 (None이면 제한 없음)
            where_clause: WHERE 조건절 (예: "created_at > '2024-01-01'")
            columns: 내보낼 컬럼 목록 (None이면 모든 컬럼)

        Returns:
            내보내기 성공 여부
        """
        try:
            # 테이블 정보 조회
            table_info = self.get_table_info(table_name, schema)
            if not table_info:
                return False

            self.logger.info(f"테이블 '{table_name}' 내보내기 시작")
            self.logger.info(f"  - 행 수: {table_info['row_count']:,}개")
            self.logger.info(f"  - 컬럼 수: {table_info['column_count']}개")

            # SQL 쿼리 구성
            if columns:
                column_str = ', '.join([f'"{col}"' for col in columns])
            else:
                column_str = '*'

            query = f'SELECT {column_str} FROM "{schema}"."{table_name}"'

            if where_clause:
                query += f' WHERE {where_clause}'

            if limit:
                query += f' LIMIT {limit}'

            self.logger.info(f"실행 쿼리: {query}")

            # 데이터 조회
            df = pd.read_sql_query(query, self.conn)
            self.logger.info(f"데이터 조회 완료: {len(df):,}행")

            # 출력 디렉토리 생성
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 엑셀 파일로 저장
            df.to_excel(output_file, index=False, engine='openpyxl')
            self.logger.info(f"엑셀 파일 저장 완료: {output_file}")
            self.logger.info(f"  - 파일 크기: {output_path.stat().st_size / 1024 / 1024:.2f} MB")

            return True

        except Exception as e:
            self.logger.error(f"테이블 내보내기 실패: {str(e)}")
            return False

    def export_all_tables(
        self,
        output_dir: str,
        schema: str = 'public',
        limit: Optional[int] = None
    ) -> dict:
        """
        스키마의 모든 테이블을 엑셀 파일로 내보낸다.

        Args:
            output_dir: 출력 디렉토리
            schema: 스키마 이름
            limit: 테이블당 최대 행 수 제한

        Returns:
            내보내기 결과 (성공/실패 테이블 목록)
        """
        try:
            # 테이블 목록 조회
            tables = self.list_tables(schema)
            if not tables:
                self.logger.warning("내보낼 테이블이 없습니다.")
                return {'success': [], 'failed': []}

            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            success_tables = []
            failed_tables = []

            for i, table_name in enumerate(tables, 1):
                self.logger.info(f"\n진행: {i}/{len(tables)} - {table_name}")

                output_file = output_path / f"{table_name}_{timestamp}.xlsx"

                if self.export_table(table_name, str(output_file), schema, limit):
                    success_tables.append(table_name)
                else:
                    failed_tables.append(table_name)

            # 결과 요약
            self.logger.info("\n" + "=" * 80)
            self.logger.info("내보내기 완료")
            self.logger.info(f"  - 성공: {len(success_tables)}개")
            self.logger.info(f"  - 실패: {len(failed_tables)}개")

            if failed_tables:
                self.logger.warning(f"실패한 테이블: {', '.join(failed_tables)}")

            return {
                'success': success_tables,
                'failed': failed_tables
            }

        except Exception as e:
            self.logger.error(f"전체 테이블 내보내기 실패: {str(e)}")
            return {'success': [], 'failed': []}

    def export_query_result(
        self,
        query: str,
        output_file: str,
        query_name: str = "custom_query"
    ) -> bool:
        """
        커스텀 SQL 쿼리 결과를 엑셀 파일로 내보낸다.

        Args:
            query: SQL 쿼리
            output_file: 출력 파일 경로
            query_name: 쿼리 이름 (로깅용)

        Returns:
            내보내기 성공 여부
        """
        try:
            self.logger.info(f"커스텀 쿼리 실행: {query_name}")
            self.logger.info(f"쿼리: {query}")

            # 쿼리 실행
            df = pd.read_sql_query(query, self.conn)
            self.logger.info(f"쿼리 결과: {len(df):,}행, {len(df.columns)}컬럼")

            # 출력 디렉토리 생성
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 엑셀 파일로 저장
            df.to_excel(output_file, index=False, engine='openpyxl')
            self.logger.info(f"엑셀 파일 저장 완료: {output_file}")

            return True

        except Exception as e:
            self.logger.error(f"커스텀 쿼리 내보내기 실패: {str(e)}")
            return False


def main():
    """메인 함수."""
    parser = argparse.ArgumentParser(
        description="PostgreSQL 테이블을 엑셀 파일로 내보내기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 단일 테이블 내보내기
  python export_table_to_excel.py --table products --output data/products.xlsx

  # 테이블 전체 내보내기 (최대 1000행)
  python export_table_to_excel.py --table products --output data/products.xlsx --limit 1000

  # WHERE 조건 추가
  python export_table_to_excel.py --table products --output data/products.xlsx --where "price > 10000"

  # 특정 컬럼만 내보내기
  python export_table_to_excel.py --table products --output data/products.xlsx --columns id,name,price

  # 모든 테이블 내보내기
  python export_table_to_excel.py --all-tables --output-dir data/exports

  # 테이블 목록 조회
  python export_table_to_excel.py --list-tables

  # 커스텀 쿼리 실행
  python export_table_to_excel.py --query "SELECT * FROM products WHERE price > 10000" --output data/custom.xlsx
        """
    )

    # 데이터베이스 연결
    parser.add_argument("--db-url", help="PostgreSQL 연결 URL (기본값: 환경변수 DATABASE_URL)")
    parser.add_argument("--schema", default="public", help="스키마 이름 (기본값: public)")

    # 작업 선택
    parser.add_argument("--list-tables", action="store_true", help="테이블 목록만 조회")
    parser.add_argument("--table-info", help="특정 테이블의 정보 조회")
    parser.add_argument("--table", help="내보낼 테이블 이름")
    parser.add_argument("--all-tables", action="store_true", help="모든 테이블 내보내기")
    parser.add_argument("--query", help="커스텀 SQL 쿼리")

    # 내보내기 옵션
    parser.add_argument("--output", help="출력 파일 경로 (단일 테이블/쿼리용)")
    parser.add_argument("--output-dir", default="data/exports", help="출력 디렉토리 (전체 테이블용)")
    parser.add_argument("--limit", type=int, help="최대 행 수 제한")
    parser.add_argument("--where", help="WHERE 조건절")
    parser.add_argument("--columns", help="내보낼 컬럼 목록 (쉼표로 구분)")

    args = parser.parse_args()

    # Exporter 초기화
    try:
        exporter = PostgresTableExporter(args.db_url)

        if not exporter.connect():
            sys.exit(1)

        # 작업 실행
        if args.list_tables:
            # 테이블 목록 조회
            tables = exporter.list_tables(args.schema)
            if tables:
                print(f"\n스키마 '{args.schema}'의 테이블 목록:")
                for i, table in enumerate(tables, 1):
                    print(f"  {i}. {table}")
            else:
                print("테이블이 없습니다.")

        elif args.table_info:
            # 테이블 정보 조회
            info = exporter.get_table_info(args.table_info, args.schema)
            if info:
                print(f"\n테이블 '{args.table_info}' 정보:")
                print(f"  - 행 수: {info['row_count']:,}개")
                print(f"  - 컬럼 수: {info['column_count']}개")
                print(f"  - 컬럼 목록:")
                for i, (col, col_type) in enumerate(zip(info['columns'], info['column_types']), 1):
                    print(f"      {i}. {col} ({col_type})")

        elif args.all_tables:
            # 모든 테이블 내보내기
            result = exporter.export_all_tables(
                args.output_dir,
                args.schema,
                args.limit
            )
            if result['success']:
                print(f"\n✅ {len(result['success'])}개 테이블 내보내기 성공")
                print(f"출력 디렉토리: {args.output_dir}")
            if result['failed']:
                print(f"\n❌ {len(result['failed'])}개 테이블 내보내기 실패")
                sys.exit(1)

        elif args.query:
            # 커스텀 쿼리 실행
            if not args.output:
                print("❌ 오류: --query 사용 시 --output은 필수입니다.")
                sys.exit(1)

            if exporter.export_query_result(args.query, args.output):
                print(f"\n✅ 쿼리 결과 내보내기 성공: {args.output}")
            else:
                print("\n❌ 쿼리 실행 실패")
                sys.exit(1)

        elif args.table:
            # 단일 테이블 내보내기
            if not args.output:
                # 기본 출력 파일명 생성
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                args.output = f"data/exports/{args.table}_{timestamp}.xlsx"

            columns = args.columns.split(',') if args.columns else None

            if exporter.export_table(
                args.table,
                args.output,
                args.schema,
                args.limit,
                args.where,
                columns
            ):
                print(f"\n✅ 테이블 내보내기 성공: {args.output}")
            else:
                print("\n❌ 테이블 내보내기 실패")
                sys.exit(1)

        else:
            # 옵션 없음
            parser.print_help()
            print("\n사용 예시를 참고하세요.")

    except Exception as e:
        logger.error(f"실행 중 오류 발생: {str(e)}")
        sys.exit(1)

    finally:
        if 'exporter' in locals():
            exporter.disconnect()


if __name__ == "__main__":
    main()

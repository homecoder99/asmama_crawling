"""데이터 저장소 인터페이스 및 구현체."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Union
from pathlib import Path
import json
import logging

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False


class BaseStorage(ABC):
    """
    데이터 저장소의 추상 베이스 클래스.
    
    Excel과 PostgreSQL 등 다양한 저장소를 지원하기 위한 인터페이스를 정의한다.
    """
    
    @abstractmethod
    def save(self, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> bool:
        """
        데이터를 저장한다.
        
        Args:
            data: 저장할 데이터 (단일 또는 리스트)
            
        Returns:
            저장 성공 여부
        """
        pass
    
    @abstractmethod
    def load(self) -> List[Dict[str, Any]]:
        """
        저장된 데이터를 로드한다.
        
        Returns:
            로드된 데이터 목록
        """
        pass
    
    @abstractmethod
    def clear(self) -> bool:
        """
        저장된 데이터를 모두 삭제한다.
        
        Returns:
            삭제 성공 여부
        """
        pass


class ExcelStorage(BaseStorage):
    """
    Excel 파일 기반 데이터 저장소.
    
    pandas와 openpyxl을 사용하여 Excel 파일에 데이터를 저장하고 로드한다.
    PostgreSQL 마이그레이션을 위해 호환 가능한 스키마를 유지한다.
    """
    
    def __init__(self, file_path: str):
        """
        Excel 저장소를 초기화한다.
        
        Args:
            file_path: Excel 파일 경로
        """
        self.file_path = Path(file_path)
        
        # 로거 설정 - setup_logger와 동일한 핸들러 사용
        from .utils import setup_logger
        self.logger = setup_logger(self.__class__.__name__)
        
        # 라이브러리 의존성 확인
        if not PANDAS_AVAILABLE:
            raise ImportError("pandas가 설치되지 않았습니다. pip install pandas를 실행하세요.")
        
        if not OPENPYXL_AVAILABLE:
            raise ImportError("openpyxl이 설치되지 않았습니다. pip install openpyxl을 실행하세요.")
        
        # 디렉토리 생성
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 기존 데이터 로드 (있는 경우)
        self.data = self._load_existing_data()
    
    def _load_existing_data(self) -> List[Dict[str, Any]]:
        """
        기존 Excel 파일에서 데이터를 로드한다.
        
        Returns:
            로드된 데이터 목록
        """
        if not self.file_path.exists():
            return []
        
        try:
            df = pd.read_excel(self.file_path)
            return df.to_dict('records')
        except Exception as e:
            self.logger.warning(f"기존 데이터 로드 실패: {str(e)}")
            return []
    
    def save(self, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> bool:
        """
        데이터를 Excel 파일에 저장한다.
        
        xlsxwriter 엔진을 사용한 빠른 저장:
        - openpyxl의 셀 단위 처리 → xlsxwriter의 행 단위 append() 사용
        - 중복 스타일 폭증 → xlsxwriter의 메모리 효율적 처리로 방지
        - UsedRange 문제 → 새 파일 생성으로 회피
        - 메모리 오버헤드 → 스트리밍 방식으로 최소화
        
        Args:
            data: 저장할 데이터 (단일 또는 리스트)
            
        Returns:
            저장 성공 여부
        """
        try:
            import xlsxwriter
            
            # 단일 데이터를 리스트로 변환
            if isinstance(data, dict):
                data = [data]

            # 기존 Excel 파일에서 데이터 로드 (메모리 절약을 위해 매번 로드)
            existing_data = []
            if self.file_path.exists():
                try:
                    existing_df = pd.read_excel(self.file_path)
                    existing_data = existing_df.to_dict('records')
                except Exception as e:
                    self.logger.warning(f"기존 파일 로드 실패 (새로 생성): {str(e)}")

            # 새 데이터 추가
            all_data = existing_data + data

            # self.data는 누적하지 않고 현재 배치만 유지 (메모리 절약)
            self.data = all_data

            # DataFrame으로 변환
            df = pd.DataFrame(all_data)
            
            # FIX ME: 스키마 변경 시 컬럼 순서 및 타입 조정 필요
            # 현재 스키마: branduid, name, price, options, image_urls, detail_html
            column_order = ['branduid', 'name', 'price', 'options', 'image_urls', 'detail_html']
            
            # 컬럼 순서 정렬 (없는 컬럼은 무시)
            existing_columns = [col for col in column_order if col in df.columns]
            additional_columns = [col for col in df.columns if col not in column_order]
            final_columns = existing_columns + additional_columns
            
            if final_columns:
                df = df[final_columns]
            
            # 리스트 타입 컬럼을 문자열로 변환 (Excel 호환성)
            for col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].apply(lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, list) else x)
            
            # xlsxwriter 엔진을 사용한 빠른 저장
            with pd.ExcelWriter(self.file_path, engine='xlsxwriter', 
                              engine_kwargs={'options': {'strings_to_urls': False}}) as writer:
                df.to_excel(writer, index=False, sheet_name='Sheet1')
            
            self.logger.info(f"데이터 저장 완료: {len(data)}개 항목 → {self.file_path}")
            return True
            
        except ImportError:
            # xlsxwriter가 없으면 기존 openpyxl 방식으로 폴백
            self.logger.warning("xlsxwriter를 찾을 수 없어 openpyxl 방식으로 저장합니다.")
            try:
                # DataFrame으로 변환
                df = pd.DataFrame(self.data)
                
                # 컬럼 순서 정렬
                column_order = ['branduid', 'name', 'price', 'options', 'image_urls', 'detail_html']
                existing_columns = [col for col in column_order if col in df.columns]
                additional_columns = [col for col in df.columns if col not in column_order]
                final_columns = existing_columns + additional_columns
                
                if final_columns:
                    df = df[final_columns]
                
                # 리스트 타입 컬럼을 문자열로 변환
                for col in df.columns:
                    if df[col].dtype == 'object':
                        df[col] = df[col].apply(lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, list) else x)
                
                # openpyxl 엔진으로 저장
                df.to_excel(self.file_path, index=False, engine='openpyxl')
                
                self.logger.info(f"데이터 저장 완료 (openpyxl): {len(data)}개 항목 → {self.file_path}")
                return True
                
            except Exception as e:
                self.logger.error(f"데이터 저장 실패 (openpyxl 폴백): {str(e)}")
                return False
            
        except Exception as e:
            self.logger.error(f"데이터 저장 실패: {str(e)}")
            return False
    
    def load(self) -> List[Dict[str, Any]]:
        """
        Excel 파일에서 데이터를 로드한다.
        
        Returns:
            로드된 데이터 목록
        """
        try:
            if not self.file_path.exists():
                return []
            
            df = pd.read_excel(self.file_path)
            
            # JSON 문자열을 리스트로 변환
            for col in df.columns:
                if col in ['options', 'image_urls']:
                    df[col] = df[col].apply(lambda x: json.loads(x) if isinstance(x, str) and x.startswith('[') else x)
            
            return df.to_dict('records')
            
        except Exception as e:
            self.logger.error(f"데이터 로드 실패: {str(e)}")
            return []
    
    def clear(self) -> bool:
        """
        Excel 파일을 삭제한다.
        
        Returns:
            삭제 성공 여부
        """
        try:
            if self.file_path.exists():
                self.file_path.unlink()
                self.data = []
                self.logger.info(f"데이터 파일 삭제 완료: {self.file_path}")
            return True
        except Exception as e:
            self.logger.error(f"데이터 파일 삭제 실패: {str(e)}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        저장된 데이터의 통계 정보를 반환한다.
        
        Returns:
            통계 정보 딕셔너리
        """
        try:
            data = self.load()
            
            if not data:
                return {"total_count": 0}
            
            df = pd.DataFrame(data)
            
            stats = {
                "total_count": len(df),
                "columns": list(df.columns),
                "file_size_mb": self.file_path.stat().st_size / (1024 * 1024) if self.file_path.exists() else 0
            }
            
            # 가격 통계 (있는 경우)
            if 'price' in df.columns:
                price_series = pd.to_numeric(df['price'], errors='coerce')
                stats["price_stats"] = {
                    "min": price_series.min(),
                    "max": price_series.max(),
                    "mean": price_series.mean(),
                    "count": price_series.count()
                }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"통계 정보 생성 실패: {str(e)}")
            return {"error": str(e)}


class JSONStorage(BaseStorage):
    """
    JSON 파일 기반 데이터 저장소.
    
    간단한 JSON 형태로 데이터를 저장한다.
    개발 및 테스트 용도로 사용.
    """
    
    def __init__(self, file_path: str):
        """
        JSON 저장소를 초기화한다.
        
        Args:
            file_path: JSON 파일 경로
        """
        self.file_path = Path(file_path)
        
        # 로거 설정 - setup_logger와 동일한 핸들러 사용
        from .utils import setup_logger
        self.logger = setup_logger(self.__class__.__name__)
        
        # 디렉토리 생성
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
    
    def save(self, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> bool:
        """
        데이터를 JSON 파일에 저장한다.
        
        Args:
            data: 저장할 데이터
            
        Returns:
            저장 성공 여부
        """
        try:
            # 기존 데이터 로드
            existing_data = self.load()
            
            # 새 데이터 추가
            if isinstance(data, dict):
                existing_data.append(data)
            else:
                existing_data.extend(data)
            
            # JSON 파일로 저장
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"JSON 데이터 저장 완료: {self.file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"JSON 데이터 저장 실패: {str(e)}")
            return False
    
    def load(self) -> List[Dict[str, Any]]:
        """
        JSON 파일에서 데이터를 로드한다.
        
        Returns:
            로드된 데이터 목록
        """
        try:
            if not self.file_path.exists():
                return []
            
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as e:
            self.logger.error(f"JSON 데이터 로드 실패: {str(e)}")
            return []
    
    def clear(self) -> bool:
        """
        JSON 파일을 삭제한다.
        
        Returns:
            삭제 성공 여부
        """
        try:
            if self.file_path.exists():
                self.file_path.unlink()
                self.logger.info(f"JSON 파일 삭제 완료: {self.file_path}")
            return True
        except Exception as e:
            self.logger.error(f"JSON 파일 삭제 실패: {str(e)}")
            return False


# FIX ME: PostgreSQL 지원을 위한 DatabaseStorage 클래스 추가 예정
# class DatabaseStorage(BaseStorage):
#     """PostgreSQL 기반 데이터 저장소 (향후 구현 예정)"""
#     pass
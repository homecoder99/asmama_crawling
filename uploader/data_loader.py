"""템플릿 파일 로딩 시스템.

Asmama 크롤링 데이터를 Qoo10 업로드 형식으로 변환하기 위한
템플릿 파일들을 로딩하는 시스템을 구현한다.
"""

import os
import pandas as pd
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging

class TemplateLoader:
    """
    템플릿 파일 로딩 담당 클래스.
    
    ban.xlsx, brand.csv, category.csv, registered.xlsx, sample.xlsx 파일을
    각각의 지정된 형식으로 로딩한다.
    """
    
    def __init__(self, templates_dir: str):
        """
        TemplateLoader 초기화.
        
        Args:
            templates_dir: 템플릿 파일들이 있는 디렉토리 경로
        """
        # uploader 디렉토리에서 실행되므로 상대 경로 조정
        self.templates_dir = Path(templates_dir)
        self.logger = logging.getLogger(__name__)
        
        # 로딩된 데이터 저장
        self.ban_data: Optional[pd.DataFrame] = None
        self.warning_data: Optional[pd.DataFrame] = None
        self.brand_data: Optional[pd.DataFrame] = None
        self.category_data: Optional[pd.DataFrame] = None
        self.registered_data: Optional[pd.DataFrame] = None
        self.sample_data: Optional[pd.DataFrame] = None
        
        # Qoo10 필수 필드 (18개)
        self.required_fields = [
            "seller_unique_item_id", "category_number", "brand_number", "item_name",
            "item_status_Y/N/D", "end_date", "price_yen", "quantity",
            "image_main_url", "header_html", "footer_html", "item_description",
            "Shipping_number", "available_shipping_date", "origin_type",
            "origin_country_id", "item_weight", "under18s_display_Y/N"
        ]
    
    def load_all_templates(self) -> bool:
        """
        모든 템플릿 파일을 로딩한다.
        
        Returns:
            모든 파일 로딩 성공 여부
        """
        try:
            # 각 템플릿 파일 로딩
            self.load_ban_list()
            self.load_brand_mapping()
            self.load_category_mapping()
            self.load_registered_products()
            self.load_sample_format()
            
            self.logger.info("모든 템플릿 파일 로딩 완료")
            return True
            
        except Exception as e:
            self.logger.error(f"템플릿 파일 로딩 실패: {str(e)}")
            return False
    
    def load_ban_list(self) -> pd.DataFrame:
        """
        금지 브랜드/키워드 목록을 로딩한다.
        
        파일: ban/ban.xlsx
        형식: skiprows=0, Row 0이 헤더 (brand, keyword)
        
        Returns:
            금지 목록 DataFrame
        """
        ban_file = self.templates_dir / "ban" / "ban.xlsx"
        
        try:
            # skiprows=0으로 읽고 Row 0을 헤더로 사용
            df = pd.read_excel(ban_file, header=0)
            
            self.ban_data = df
            self.logger.info(f"금지 목록 로딩 완료: {len(df)}개 항목")
            return df
            
        except Exception as e:
            self.logger.error(f"금지 목록 로딩 실패: {str(e)}")
            return pd.DataFrame()
    
    def load_brand_mapping(self) -> pd.DataFrame:
        """
        브랜드 매핑 정보를 로딩한다.
        
        파일: brand/brand.csv
        형식: Brand No ↔ Brand Title, encoding="utf-8-sig", dtype=str (앞자리 0 유지)
        
        Returns:
            브랜드 매핑 DataFrame
        """
        brand_file = self.templates_dir / "brand" / "brand.csv"
        
        try:
            # dtype=str로 읽어서 앞자리 0 유지, utf-8-sig 인코딩
            df = pd.read_csv(brand_file, dtype=str, encoding="utf-8-sig")
            
            self.brand_data = df
            self.logger.info(f"브랜드 매핑 로딩 완료: {len(df)}개 브랜드")
            return df
            
        except Exception as e:
            self.logger.error(f"브랜드 매핑 로딩 실패: {str(e)}")
            return pd.DataFrame()
    
    def load_category_mapping(self) -> pd.DataFrame:
        """
        카테고리 매핑 정보를 로딩한다.
        
        파일: category/Qoo10_CategoryInfo.csv
        형식: 대·중·소 코드(9자리) ↔ 카테고리명, encoding="utf-8-sig", dtype=str
        
        Returns:
            카테고리 매핑 DataFrame
        """
        category_file = self.templates_dir / "category" / "Qoo10_CategoryInfo.csv"
        
        try:
            # dtype=str로 읽어서 앞자리 0 유지, utf-8-sig 인코딩
            df = pd.read_csv(category_file, dtype=str, encoding="utf-8-sig")
            
            self.category_data = df
            self.logger.info(f"카테고리 매핑 로딩 완료: {len(df)}개 카테고리")
            return df
            
        except Exception as e:
            self.logger.error(f"카테고리 매핑 로딩 실패: {str(e)}")
            return pd.DataFrame()
    
    def load_registered_products(self) -> pd.DataFrame:
        """
        기등록 상품 목록을 로딩한다.
        
        파일: registered/registered.xlsx
        형식: sample.xlsx와 동일 구조, skiprows=4 후 Row0을 컬럼명으로 지정
        
        Returns:
            기등록 상품 DataFrame
        """
        registered_file = self.templates_dir / "registered" / "registered.xlsx"
        
        try:
            # skiprows=4로 읽고 첫 번째 행을 컬럼명으로 사용
            df = pd.read_excel(registered_file, header=None, skiprows=4)
            
            if not df.empty:
                # 첫 번째 행을 컬럼명으로 설정
                df.columns = df.iloc[0]
                df = df.drop(df.index[0]).reset_index(drop=True)
            
            self.registered_data = df
            self.logger.info(f"기등록 상품 로딩 완료: {len(df)}개 상품")
            return df
            
        except Exception as e:
            self.logger.error(f"기등록 상품 로딩 실패: {str(e)}")
            return pd.DataFrame()
    
    def load_sample_format(self) -> pd.DataFrame:
        """
        업로드 샘플 형식을 로딩한다.
        
        파일: upload/sample.xlsx
        형식: skiprows=4 후 Row0을 컬럼명으로 지정 (48개 필드)
        Row 0: field keys (snake_case, 48개) ← DataFrame.columns로 사용
        Row 1: 한글 필드명
        Row 2: "필수입력/선택입력" 표기
        Row 3: 작성 가이드
        Row 4~: 실제 데이터
        
        Returns:
            샘플 형식 DataFrame
        """
        sample_file = self.templates_dir / "upload" / "sample.xlsx"
        
        try:
            # skiprows=4로 읽고 첫 번째 행을 컬럼명으로 사용
            df = pd.read_excel(sample_file, header=None, skiprows=4)
            
            if not df.empty:
                # 첫 번째 행을 컬럼명으로 설정
                df.columns = df.iloc[0]
                df = df.drop(df.index[0]).reset_index(drop=True)
            
            self.sample_data = df
            self.logger.info(f"샘플 형식 로딩 완료: {len(df.columns)}개 필드")
            return df
            
        except Exception as e:
            self.logger.error(f"샘플 형식 로딩 실패: {str(e)}")
            return pd.DataFrame()
    
    def get_warning_keywords(self) -> List[str]:
        """
        경고 키워드 목록을 반환한다.
        
        Returns:
            경고 키워드 목록
        """
        if self.warning_data is None or self.warning_data.empty:
            return []
        
        keywords = []
        # keyword 컬럼이 있는 경우
        if 'keyword' in self.warning_data.columns:
            keywords.extend(self.warning_data['keyword'].dropna().astype(str).tolist())
        
        return [kw.strip() for kw in keywords if kw.strip()]
    
    def get_ban_brands(self) -> List[str]:
        """
        금지 브랜드 목록을 반환한다.
        
        Returns:
            금지 브랜드 목록
        """
        if self.ban_data is None or self.ban_data.empty:
            return []
        
        brands = []
        # brand 컬럼이 있는 경우
        if 'brand' in self.ban_data.columns:
            brands.extend(self.ban_data['brand'].dropna().astype(str).tolist())
        
        return [brand.strip() for brand in brands if brand.strip()]
    
    def get_registered_unique_item_ids(self) -> List[str]:
        """
        기등록 상품의 seller_unique_item_id 목록을 반환한다.
        
        Returns:
            기등록 unique_item_id 목록
        """
        if self.registered_data is None or self.registered_data.empty:
            return []
        
        unique_ids = []
        # seller_unique_item_id 컬럼에서 추출
        if 'seller_unique_item_id' in self.registered_data.columns:
            unique_ids.extend(self.registered_data['seller_unique_item_id'].dropna().astype(str).tolist())
        
        return [uid.strip() for uid in unique_ids if uid.strip()]
    
    def get_sample_columns(self) -> List[str]:
        """
        샘플 형식의 컬럼 목록을 반환한다 (48개 필드).
        
        Returns:
            샘플 컬럼 목록
        """
        if self.sample_data is None or self.sample_data.empty:
            return []
        
        return self.sample_data.columns.tolist()
    
    def is_category_valid(self, category_name: str) -> bool:
        """
        카테고리명이 유효한지 확인한다.
        
        Args:
            category_name: 확인할 카테고리명
            
        Returns:
            카테고리 유효 여부
        """
        if self.category_data is None or self.category_data.empty:
            return False
        
        # 카테고리 데이터에서 해당 카테고리명 검색
        for col in self.category_data.columns:
            if category_name in self.category_data[col].astype(str).values:
                return True
        
        return False
    
    def get_brand_number(self, brand_name: str) -> Optional[str]:
        """
        브랜드명에 해당하는 브랜드 번호를 반환한다.
        
        Args:
            brand_name: 브랜드명
            
        Returns:
            브랜드 번호 또는 None
        """
        if self.brand_data is None or self.brand_data.empty:
            return None
        
        # 브랜드명으로 검색하여 번호 반환
        for idx, row in self.brand_data.iterrows():
            if brand_name in row.values:
                # 첫 번째 컬럼을 번호로 가정
                return str(row.iloc[0])
        
        return None
    
    def get_category_number(self, category_name: str) -> Optional[str]:
        """
        카테고리명에 해당하는 카테고리 번호(9자리)를 반환한다.
        
        Args:
            category_name: 카테고리명
            
        Returns:
            카테고리 번호 또는 None
        """
        if self.category_data is None or self.category_data.empty:
            return None
        
        # 카테고리명으로 검색하여 번호 반환
        for idx, row in self.category_data.iterrows():
            if category_name in row.values:
                # 첫 번째 컬럼을 번호로 가정
                return str(row.iloc[0])
        
        return None
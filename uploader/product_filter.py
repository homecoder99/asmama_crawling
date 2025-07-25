"""상품 필터링 시스템.

템플릿 데이터를 기반으로 금지 브랜드, 경고 키워드 처리, 이미지 필터링 결과를 통해
업로드 가능한 상품만 필터링하는 시스템을 구현한다.
"""

import re
from typing import Dict, Any, List, Optional, Tuple
import logging
from openai import OpenAI
import os
import dotenv
from data_loader import TemplateLoader

# 환경변수 로드
dotenv.load_dotenv()

class ProductFilter:
    """
    상품 필터링 담당 클래스.
    
    금지 브랜드/경고 키워드 검증, 기등록 상품 검증, 이미지 필터링 결과를 통해
    업로드 가능한 상품만 선별한다. 경고 키워드가 있으면 AI로 상품명을 수정한다.
    """
    
    def __init__(self, template_loader: TemplateLoader):
        """
        ProductFilter 초기화.
        
        Args:
            template_loader: 로딩된 템플릿 데이터
        """
        self.logger = logging.getLogger(__name__)
        self.template_loader = template_loader
        
        # OpenAI 클라이언트 초기화 (상품명 수정용)
        self.openai_client = OpenAI()
        self.openai_client.api_key = os.getenv("OPENAI_API_KEY")
        
        # 캐시
        self._warning_keywords_cache = None
        self._ban_brands_cache = None
        self._registered_branduids_cache = None
    
    def filter_products(self, products: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        상품 목록을 필터링한다.
        
        Args:
            products: 필터링할 상품 목록 (이미 validator.py에서 필수값 검증 완료)
            
        Returns:
            (필터링된_상품_목록, 필터링_통계)
        """
        self.logger.info(f"상품 필터링 시작: {len(products)}개 상품")
        
        # 필터링 통계
        stats = {
            "total_products": len(products),
            "filtered_products": 0,
            "removed_products": 0,
            "modified_products": 0,
            "removal_reasons": {
                "banned_brand": 0,
                "already_registered": 0,
                "no_representative_image": 0,
                "invalid_category": 0,
                "no_category_mapping": 0,
                "no_brand_mapping": 0,
                "missing_required_fields": 0
            },
            "modifications": {
                "warning_keyword_fixed": 0
            },
            "detailed_removals": [],
            "detailed_modifications": []
        }
        
        filtered_products = []
        
        for product in products:
            branduid = product.get("branduid", "unknown")
            
            # 1. 대표 이미지 필수 검증 (이미지 필터링 결과 확인)
            if not self._has_representative_image(product):
                stats["removal_reasons"]["no_representative_image"] += 1
                stats["detailed_removals"].append({
                    "branduid": branduid,
                    "reason": "no_representative_image",
                    "details": "대표 이미지 없음"
                })
                continue
            
            # 2. 금지 브랜드 검증
            if self._is_banned_brand(product):
                stats["removal_reasons"]["banned_brand"] += 1
                stats["detailed_removals"].append({
                    "branduid": branduid,
                    "reason": "banned_brand",
                    "details": product.get("brand_name", "")
                })
                continue
            
            # 3. 기등록 상품 검증
            if self._is_already_registered(product):
                stats["removal_reasons"]["already_registered"] += 1
                stats["detailed_removals"].append({
                    "branduid": branduid,
                    "reason": "already_registered",
                    "details": branduid
                })
                continue
            
            # 4. 카테고리 유효성 검증
            if not self._is_valid_category(product):
                stats["removal_reasons"]["invalid_category"] += 1
                stats["detailed_removals"].append({
                    "branduid": branduid,
                    "reason": "invalid_category",
                    "details": product.get("category_name", "")
                })
                continue
            
            # 5. 카테고리 번호 매핑 가능성 검증
            if not self._can_map_category(product):
                stats["removal_reasons"]["no_category_mapping"] += 1
                stats["detailed_removals"].append({
                    "branduid": branduid,
                    "reason": "no_category_mapping",
                    "details": product.get("category_name", "")
                })
                continue
            
            # 6. 브랜드 번호 매핑 가능성 검증
            if not self._can_map_brand(product):
                stats["removal_reasons"]["no_brand_mapping"] += 1
                stats["detailed_removals"].append({
                    "branduid": branduid,
                    "reason": "no_brand_mapping",
                    "details": product.get("brand_name", "")
                })
                continue
            
            # 7. 필수 필드 존재 여부 검증
            missing_field = self._check_required_fields(product)
            if missing_field:
                stats["removal_reasons"]["missing_required_fields"] += 1
                stats["detailed_removals"].append({
                    "branduid": branduid,
                    "reason": "missing_required_fields",
                    "details": missing_field
                })
                continue
            
            # 8. 경고 키워드 검증 및 AI 수정
            warning_keyword = self._contains_warning_keyword(product)
            if warning_keyword:
                modified_product = self._fix_warning_keyword(product, warning_keyword)
                if modified_product:
                    stats["modifications"]["warning_keyword_fixed"] += 1
                    stats["modified_products"] += 1
                    stats["detailed_modifications"].append({
                        "branduid": branduid,
                        "warning_keyword": warning_keyword,
                        "original_name": product.get("item_name", ""),
                        "modified_name": modified_product.get("item_name", "")
                    })
                    product = modified_product
                else:
                    # AI 수정 실패 시 원본 유지하고 경고 로그
                    self.logger.warning(f"경고 키워드 수정 실패: {branduid} - {warning_keyword}")
            
            # 모든 검증 통과
            filtered_products.append(product)
        
        stats["filtered_products"] = len(filtered_products)
        stats["removed_products"] = stats["total_products"] - stats["filtered_products"]
        
        self.logger.info(f"상품 필터링 완료: {stats['filtered_products']}/{stats['total_products']}개 통과 "
                        f"({stats['filtered_products']/stats['total_products']*100:.1f}%) "
                        f"수정: {stats['modified_products']}개")
        
        return filtered_products, stats
    
    def _has_representative_image(self, product: Dict[str, Any]) -> bool:
        """
        대표 이미지가 있는지 확인한다 (이미지 필터링 결과 기준).
        
        Args:
            product: 상품 데이터
            
        Returns:
            대표 이미지 존재 여부
        """
        representative_image = str(product.get("representative_image", "")).strip()
        return bool(representative_image and ("http" in representative_image.lower() or representative_image.startswith("/")))
    
    def _is_banned_brand(self, product: Dict[str, Any]) -> bool:
        """
        금지 브랜드인지 확인한다.
        
        Args:
            product: 상품 데이터
            
        Returns:
            금지 브랜드 여부
        """
        if self._ban_brands_cache is None:
            self._ban_brands_cache = self.template_loader.get_ban_brands()
        
        brand_name = str(product.get("brand_name", "")).strip().lower()
        if not brand_name:
            return False
        
        for banned_brand in self._ban_brands_cache:
            if banned_brand.lower() in brand_name:
                return True
        
        return False
    
    def _contains_warning_keyword(self, product: Dict[str, Any]) -> Optional[str]:
        """
        경고 키워드(의학, 광고성 문구)가 포함되어 있는지 확인한다.
        
        Args:
            product: 상품 데이터
            
        Returns:
            발견된 경고 키워드 또는 None
        """
        if self._warning_keywords_cache is None:
            self._warning_keywords_cache = self.template_loader.get_warning_keywords()
        
        # 검사할 텍스트 필드들 (주로 상품명)
        text_fields = [
            product.get("item_name", ""),
            product.get("summary_description", "")
        ]
        
        search_text = " ".join(text_fields).lower()
        
        for keyword in self._warning_keywords_cache:
            if keyword.lower() in search_text:
                return keyword
        
        return None
    
    def _fix_warning_keyword(self, product: Dict[str, Any], warning_keyword: str) -> Optional[Dict[str, Any]]:
        """
        경고 키워드가 포함된 상품명을 AI로 수정한다.
        
        Args:
            product: 상품 데이터
            warning_keyword: 발견된 경고 키워드
            
        Returns:
            수정된 상품 데이터 또는 None (실패 시)
        """
        try:
            original_name = product.get("item_name", "")
            category = product.get("category_name", "")
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=100,
                messages=[
                    {
                        "role": "system",
                        "content": """당신은 온라인 쇼핑몰 상품명 수정 전문가입니다. 
경고 키워드(의학적 표현, 홍보성 광고 문구)가 포함된 상품명을 자연스럽게 수정해주세요.

규칙:
1. 경고 키워드를 제거하거나 순화된 표현으로 변경
2. 상품의 본질적 특성은 유지
3. 자연스럽고 매력적인 표현 사용
4. 한국어로 응답
5. 상품명만 응답 (설명 없음)"""
                    },
                    {
                        "role": "user",
                        "content": f"""상품명: "{original_name}"
카테고리: "{category}"
경고 키워드: "{warning_keyword}"

위 상품명에서 경고 키워드를 제거하거나 순화하여 새로운 상품명을 만들어주세요."""
                    }
                ]
            )
            
            modified_name = response.choices[0].message.content.strip()
            
            # 수정된 상품 데이터 반환
            modified_product = product.copy()
            modified_product["item_name"] = modified_name
            
            self.logger.info(f"상품명 수정 완료: {product.get('branduid')} - "
                           f"'{original_name}' → '{modified_name}'")
            
            return modified_product
            
        except Exception as e:
            self.logger.error(f"상품명 수정 실패: {product.get('branduid')} - {str(e)}")
            return None
    
    def _is_already_registered(self, product: Dict[str, Any]) -> bool:
        """
        이미 등록된 상품인지 확인한다 (unique_item_id 기준).
        
        Args:
            product: 상품 데이터
            
        Returns:
            기등록 상품 여부
        """
        if self._registered_branduids_cache is None:
            self._registered_branduids_cache = self.template_loader.get_registered_unique_item_ids()
        
        unique_item_id = str(product.get("unique_item_id", "")).strip()
        if not unique_item_id:
            return False
        
        return unique_item_id in self._registered_branduids_cache
    
    def _is_valid_category(self, product: Dict[str, Any]) -> bool:
        """
        카테고리가 유효한지 확인한다.
        
        Args:
            product: 상품 데이터
            
        Returns:
            카테고리 유효 여부
        """
        category_name = str(product.get("category_name", "")).strip()
        if not category_name:
            return False
        
        # 기본 카테고리는 허용
        if category_name in ["기타", "액세서리", "주얼리", "팔찌", "귀걸이", "반지", "목걸이", "헤어핀", "헤어밴드", "헤어끈"]:
            return True
        
        return self.template_loader.is_category_valid(category_name)
    
    def _can_map_category(self, product: Dict[str, Any]) -> bool:
        """
        카테고리 번호로 매핑이 가능한지 확인한다.
        
        Args:
            product: 상품 데이터
            
        Returns:
            카테고리 매핑 가능 여부
        """
        category_name = str(product.get("category_name", "")).strip()
        if not category_name:
            return False
        
        # 주얼리 및 액세서리 카테고리 키워드 매핑
        jewelry_categories = {
            "목걸이": "300002342",
            "반지": "320001121",
            "발찌": "320001451",
            "팔찌": "320001452",
            "귀찌": "320001455",
            "귀걸이": "320001456",
            "피어싱": "320001457",
            "브로치": "320001458",
            "참": "320001459",
            "케어용품": "320001453",
            "쥬얼리박스": "320001454",
            "헤어핀": "300000125",
            "헤어밴드": "300000126",
            "헤어액세서리": "300000127",
            "머리끈": "300002180",
            "헤어집게": "300003087",
        }
        
        # 카테고리 매칭 확인
        if category_name in jewelry_categories:
            return True
        
        return False
    
    def _can_map_brand(self, product: Dict[str, Any]) -> bool:
        """
        브랜드 번호로 매핑이 가능한지 확인한다.
        
        Args:
            product: 상품 데이터
            
        Returns:
            브랜드 매핑 가능 여부
        """
        brand_name = str(product.get("brand_name", "")).strip()
        if not brand_name:
            return False
        
        # ASMAMA 브랜드는 항상 매핑 가능
        if "asmama" in brand_name.lower():
            return True
        
        # 다른 브랜드는 템플릿 데이터에서 확인
        brand_number = self.template_loader.get_brand_number(brand_name)
        return brand_number is not None
    
    def _check_required_fields(self, product: Dict[str, Any]) -> str:
        """
        필수 필드가 존재하는지 확인한다.
        
        Args:
            product: 상품 데이터
            
        Returns:
            누락된 필드명 (없으면 빈 문자열)
        """
        # 필수 필드 목록
        required_fields = [
            "unique_item_id",
            "item_name",
            "price"
        ]
        
        for field in required_fields:
            value = product.get(field, "")
            if not value or (isinstance(value, str) and not value.strip()):
                return field
        
        # 가격이 0 이하인 경우
        try:
            price = product.get("price", 0)
            if isinstance(price, str):
                price = int(price.replace(",", "")) if price.replace(",", "").isdigit() else 0
            if price <= 0:
                return "price (가격이 0 이하)"
        except:
            return "price (가격 형식 오류)"
        
        return ""
    
    def get_filter_summary(self, stats: Dict[str, Any]) -> str:
        """
        필터링 결과 요약을 생성한다.
        
        Args:
            stats: 필터링 통계
            
        Returns:
            요약 문자열
        """
        summary = []
        summary.append("🔍 상품 필터링 결과")
        summary.append("=" * 50)
        summary.append("")
        
        # 전체 통계
        total = stats["total_products"]
        filtered = stats["filtered_products"]
        removed = stats["removed_products"]
        modified = stats["modified_products"]
        success_rate = (filtered / total * 100) if total > 0 else 0
        
        summary.append(f"📊 전체 통계:")
        summary.append(f"  총 상품 수: {total:,}개")
        summary.append(f"  통과 상품 수: {filtered:,}개")
        summary.append(f"  제거 상품 수: {removed:,}개")
        summary.append(f"  수정 상품 수: {modified:,}개")
        summary.append(f"  통과율: {success_rate:.1f}%")
        summary.append("")
        
        # 제거 이유별 통계
        if removed > 0:
            summary.append("❌ 제거 이유별 통계:")
            reasons = stats["removal_reasons"]
            summary.append(f"  대표 이미지 없음: {reasons['no_representative_image']}개")
            summary.append(f"  금지 브랜드: {reasons['banned_brand']}개")
            summary.append(f"  기등록 상품: {reasons['already_registered']}개")
            summary.append(f"  유효하지 않은 카테고리: {reasons['invalid_category']}개")
            summary.append(f"  카테고리 매핑 불가: {reasons['no_category_mapping']}개")
            summary.append(f"  브랜드 매핑 불가: {reasons['no_brand_mapping']}개")
            summary.append(f"  필수 필드 누락: {reasons['missing_required_fields']}개")
            summary.append("")
        
        # 수정 통계
        if modified > 0:
            summary.append("✏️ 수정 통계:")
            modifications = stats["modifications"]
            summary.append(f"  경고 키워드 수정: {modifications['warning_keyword_fixed']}개")
            summary.append("")
        
        # 상세 제거 예시 (최대 5개)
        detailed_removals = stats["detailed_removals"][:5]
        if detailed_removals:
            summary.append("📋 제거된 상품 예시 (최대 5개):")
            for removal in detailed_removals:
                summary.append(f"  • {removal['branduid']}: {removal['reason']} - {removal['details']}")
            summary.append("")
        
        # 상세 수정 예시 (최대 5개)
        detailed_modifications = stats["detailed_modifications"][:5]
        if detailed_modifications:
            summary.append("✏️ 수정된 상품 예시 (최대 5개):")
            for modification in detailed_modifications:
                summary.append(f"  • {modification['branduid']}: '{modification['original_name']}' → '{modification['modified_name']}'")
        
        return "\n".join(summary)
    
    def clear_cache(self):
        """
        캐시된 데이터를 정리한다.
        """
        self._warning_keywords_cache = None
        self._ban_brands_cache = None
        self._registered_branduids_cache = None
        self.logger.info("필터링 캐시 정리 완료")
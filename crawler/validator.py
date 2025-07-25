"""제품 데이터 검증 및 정리 시스템."""

import json
import re
import math
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from .utils import setup_logger


def safe_str(value: Any) -> str:
    """
    안전하게 값을 문자열로 변환한다.
    
    NaN, None, float 값들을 빈 문자열로 처리하고,
    다른 값들은 문자열로 변환한다.
    
    Args:
        value: 변환할 값
        
    Returns:
        안전하게 변환된 문자열
    """
    if value is None:
        return ""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def safe_strip(value: Any) -> str:
    """
    안전하게 값을 문자열로 변환하고 공백을 제거한다.
    
    Args:
        value: 변환할 값
        
    Returns:
        공백이 제거된 문자열
    """
    return safe_str(value).strip()


def is_empty_value(value: Any) -> bool:
    """
    값이 비어있는지 확인한다.
    
    NaN, None, 빈 문자열, 공백만 있는 문자열을 모두 비어있다고 판단한다.
    
    Args:
        value: 확인할 값
        
    Returns:
        비어있는지 여부
    """
    if value is None:
        return True
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


@dataclass
class ValidationStats:
    """
    검증 통계 데이터 클래스.
    """
    total_products: int = 0
    valid_products: int = 0
    removed_products: int = 0
    
    # 제거 이유별 통계
    missing_required_fields: int = 0
    invalid_price: int = 0
    missing_images: int = 0
    missing_origin_country: int = 0
    missing_category_name: int = 0
    option_inconsistency: int = 0
    discontinued_products: int = 0
    missing_celeb_info: int = 0
    duplicate_branduid: int = 0
    
    # 상세 제거 이유
    removal_reasons: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.removal_reasons is None:
            self.removal_reasons = []
    
    def add_removal_reason(self, branduid: str, reason: str, details: str = ""):
        """
        제거 이유를 기록한다.
        
        Args:
            branduid: 제품 branduid
            reason: 제거 이유
            details: 상세 설명
        """
        self.removal_reasons.append({
            "branduid": branduid,
            "reason": reason,
            "details": details
        })
    
    def to_dict(self) -> Dict[str, Any]:
        """통계 정보를 딕셔너리로 변환한다."""
        return {
            "summary": {
                "total_products": self.total_products,
                "valid_products": self.valid_products,
                "removed_products": self.removed_products,
                "success_rate": (self.valid_products / self.total_products * 100) if self.total_products > 0 else 0
            },
            "removal_breakdown": {
                "missing_required_fields": self.missing_required_fields,
                "invalid_price": self.invalid_price,
                "missing_images": self.missing_images,
                "missing_origin_country": self.missing_origin_country,
                "missing_category_name": self.missing_category_name,
                "option_inconsistency": self.option_inconsistency,
                "discontinued_products": self.discontinued_products,
                "missing_celeb_info": self.missing_celeb_info,
                "duplicate_branduid": self.duplicate_branduid
            },
            "detailed_reasons": self.removal_reasons
        }


class ProductValidator:
    """
    제품 데이터 검증 및 정리 담당 클래스.
    
    크롤링된 제품 데이터에서 필수 정보 누락, 옵션 불일치, 
    판매종료 상품을 감지하여 제거하고 통계를 생성한다.
    """
    
    # 필수 필드 정의 (사용자 요구사항 반영)
    REQUIRED_FIELDS = [
        "category_name",    # 카테고리
        "item_name",        # 상품명
        "price",           # 가격
        "images",          # 이미지
        "origin_country"   # 원산지
    ]
    
    def __init__(self, require_celeb_info: bool = True):
        """
        ProductValidator 초기화.
        
        Args:
            require_celeb_info: 관련 셀럽 정보 필수 여부
        """
        self.logger = setup_logger(self.__class__.__name__)
        self.stats = ValidationStats()
        self.require_celeb_info = require_celeb_info
        
        # 셀럽 정보가 필수인 경우 필수 필드에 추가
        if self.require_celeb_info:
            self.required_fields = self.REQUIRED_FIELDS + ["related_celeb"]
        else:
            self.required_fields = self.REQUIRED_FIELDS.copy()
    
    def validate_products(self, products: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], ValidationStats]:
        """
        제품 목록을 검증하고 유효한 제품만 반환한다.
        
        Args:
            products: 검증할 제품 데이터 목록
            
        Returns:
            (유효한_제품_목록, 검증_통계)
        """
        self.stats = ValidationStats()
        self.stats.total_products = len(products)
        
        self.logger.info(f"제품 데이터 검증 시작: {len(products)}개 제품 "
                        f"(셀럽정보 필수: {self.require_celeb_info})")
        
        # 중복 branduid 검사 및 제거
        seen_branduids = set()
        unique_products = []
        
        for product in products:
            branduid = safe_str(product.get("branduid", "")).strip()
            if branduid:
                if branduid not in seen_branduids:
                    seen_branduids.add(branduid)
                    unique_products.append(product)
                else:
                    self.stats.duplicate_branduid += 1
                    self.stats.add_removal_reason(
                        branduid,
                        "duplicate_branduid", 
                        f"중복된 branduid: {branduid}"
                    )
                    self.logger.debug(f"중복된 branduid로 제거: {branduid}")
            else:
                unique_products.append(product)  # branduid가 없는 경우는 일단 유지 (다른 검증에서 처리)
        
        if len(unique_products) < len(products):
            removed_duplicates = len(products) - len(unique_products)
            self.logger.info(f"중복 branduid {removed_duplicates}개 제거: {len(products)} → {len(unique_products)}")
        
        valid_products = []
        
        for product in unique_products:

            # 단계별 검증 수행
            if not self._validate_required_fields(product):
                continue

            if self._is_discontinued_product(product):
                continue
            
            if not self._validate_price(product):
                continue
                
            if not self._validate_images(product):
                continue
                
            if not self._validate_origin_country(product):
                continue
                
            if not self._validate_category_name(product):
                continue

            if not self._validate_option_consistency(product):
                continue
                
            if self.require_celeb_info and not self._validate_celeb_info(product):
                continue
            
            # 모든 검증 통과
            cleaned_product = self._clean_and_standardize(product)
            valid_products.append(cleaned_product)
        
        self.stats.valid_products = len(valid_products)
        self.stats.removed_products = self.stats.total_products - self.stats.valid_products
        
        self.logger.info(f"제품 검증 완료: {self.stats.valid_products}/{self.stats.total_products}개 유효 "
                        f"({self.stats.valid_products/self.stats.total_products*100:.1f}%)")
        
        return valid_products, self.stats
    
    def _validate_required_fields(self, product: Dict[str, Any]) -> bool:
        """
        필수 필드 존재 여부를 검증한다.
        
        Args:
            product: 제품 데이터
            
        Returns:
            필수 필드 모두 존재하는지 여부
        """
        branduid = safe_str(product.get("branduid", "unknown"))
        missing_fields = []
        
        for field in self.required_fields:
            value = product.get(field)
            if is_empty_value(value):
                missing_fields.append(field)
        
        if missing_fields:
            self.stats.missing_required_fields += 1
            self.stats.add_removal_reason(
                branduid, 
                "missing_required_fields", 
                f"누락된 필수 필드: {', '.join(missing_fields)}"
            )
            self.logger.debug(f"필수 필드 누락으로 제거: {branduid} - {missing_fields}")
            return False
        
        return True
    
    def _validate_price(self, product: Dict[str, Any]) -> bool:
        """
        가격 정보 유효성을 검증한다.
        
        Args:
            product: 제품 데이터
            
        Returns:
            가격 정보 유효 여부
        """
        branduid = safe_str(product.get("branduid", "unknown"))
        price = product.get("price")
        
        # NaN이나 빈 값 처리
        if is_empty_value(price):
            self.stats.invalid_price += 1
            self.stats.add_removal_reason(
                branduid,
                "invalid_price",
                "가격 정보 없음"
            )
            self.logger.debug(f"가격 정보 없음으로 제거: {branduid}")
            return False
        
        # 가격이 숫자이고 0보다 큰지 확인
        if not isinstance(price, (int, float)) or price <= 0:
            # 문자열인 경우 숫자 추출 시도
            price_str = safe_str(price)
            if price_str:
                price_numbers = re.findall(r'\d+', price_str.replace(',', ''))
                if price_numbers:
                    try:
                        price_value = int(''.join(price_numbers))
                        if price_value > 0:
                            product["price"] = price_value  # 정리된 가격으로 업데이트
                            return True
                    except ValueError:
                        pass
            
            self.stats.invalid_price += 1
            self.stats.add_removal_reason(
                branduid,
                "invalid_price",
                f"유효하지 않은 가격: {safe_str(price)}"
            )
            self.logger.debug(f"유효하지 않은 가격으로 제거: {branduid} - {price}")
            return False
        
        return True
    
    def _validate_images(self, product: Dict[str, Any]) -> bool:
        """
        이미지 정보 유효성을 검증한다.
        
        Args:
            product: 제품 데이터
            
        Returns:
            이미지 정보 유효 여부
        """
        branduid = safe_str(product.get("branduid", "unknown"))
        images = safe_str(product.get("images", ""))
        
        # 이미지 URL이 최소 1개 이상 있는지 확인
        if is_empty_value(images):
            self.stats.missing_images += 1
            self.stats.add_removal_reason(
                branduid,
                "missing_images",
                "이미지 URL 없음"
            )
            self.logger.debug(f"이미지 없음으로 제거: {branduid}")
            return False
        
        # 이미지 URL이 유효한 형식인지 간단 검증
        if not ("http" in images.lower() or images.startswith("/")):
            self.stats.missing_images += 1
            self.stats.add_removal_reason(
                branduid,
                "missing_images", 
                f"유효하지 않은 이미지 URL: {images[:50]}..."
            )
            self.logger.debug(f"유효하지 않은 이미지 URL로 제거: {branduid}")
            return False
        
        return True
    
    def _validate_origin_country(self, product: Dict[str, Any]) -> bool:
        """
        원산지 정보 유효성을 검증한다.
        
        Args:
            product: 제품 데이터
            
        Returns:
            원산지 정보 유효 여부
        """
        branduid = safe_str(product.get("branduid", "unknown"))
        origin_country = product.get("origin_country")
        
        # 원산지 정보가 있는지 확인
        if is_empty_value(origin_country):
            self.stats.missing_origin_country += 1
            self.stats.add_removal_reason(
                branduid,
                "missing_origin_country",
                "원산지 정보 없음"
            )
            self.logger.debug(f"원산지 정보 없음으로 제거: {branduid}")
            return False
        
        return True
    
    def _validate_category_name(self, product: Dict[str, Any]) -> bool:
        """
        카테고리 유효성을 검증한다.
        
        Args:
            product: 제품 데이터
            
        Returns:
            카테고리 정보 유효 여부
        """
        branduid = safe_str(product.get("branduid", "unknown"))
        category_name = product.get("category_name")
        
        # 카테고리 정보가 있는지 확인
        if is_empty_value(category_name):
            self.stats.missing_category_name += 1
            self.stats.add_removal_reason(
                branduid,
                "missing_category_name",
                "카테고리 정보 없음"
            )
            self.logger.debug(f"카테고리 정보 없음으로 제거: {branduid}")
            return False
        
        return True

    def _validate_option_consistency(self, product: Dict[str, Any]) -> bool:
        """
        옵션 정보 일치성을 검증한다 (논리적 오류 검사).
        
        Args:
            product: 제품 데이터
            
        Returns:
            옵션 정보 일치 여부
        """
        branduid = safe_str(product.get("branduid", "unknown"))
        is_option_available = product.get("is_option_available", False)
        option_info = safe_str(product.get("option_info", ""))
        
        # 논리적 오류 1: 옵션이 있다고 표시되었는데 실제 옵션 정보가 없는 경우
        if is_option_available and is_empty_value(option_info):
            self.stats.option_inconsistency += 1
            self.stats.add_removal_reason(
                branduid,
                "option_inconsistency",
                "옵션 가능으로 표시되었으나 옵션 정보 없음"
            )
            self.logger.debug(f"옵션 정보 불일치로 제거: {branduid} - 옵션 표시 있으나 정보 없음")
            return False
        
        # 논리적 오류 2: 옵션이 없다고 표시되었는데 옵션 정보가 있는 경우
        if not is_option_available and not is_empty_value(option_info):
            self.stats.option_inconsistency += 1
            self.stats.add_removal_reason(
                branduid,
                "option_inconsistency",
                "옵션 불가능으로 표시되었으나 옵션 정보 존재"
            )
            self.logger.debug(f"옵션 정보 불일치로 제거: {branduid} - 옵션 표시 없으나 정보 있음")
            return False
        
        # 옵션 정보가 있는 경우 형식 검증
        if not is_empty_value(option_info):
            # 지정된 형식 검증: 옵션명||*옵션값||*옵션가격||*재고수량||*판매자옵션코드$$
            if "||*" not in option_info:
                self.stats.option_inconsistency += 1
                self.stats.add_removal_reason(
                    branduid,
                    "option_inconsistency",
                    f"옵션 정보 형식 오류: {option_info[:50]}..."
                )
                self.logger.debug(f"옵션 형식 오류로 제거: {branduid}")
                return False
        
        return True
    
    def _validate_celeb_info(self, product: Dict[str, Any]) -> bool:
        """
        관련 셀럽 정보 존재 여부를 검증한다.
        
        Args:
            product: 제품 데이터
            
        Returns:
            셀럽 정보 유효 여부
        """
        branduid = safe_str(product.get("branduid", "unknown"))
        related_celeb = product.get("related_celeb")
        
        # 셀럽 정보가 있는지 확인
        if is_empty_value(related_celeb):
            self.stats.missing_celeb_info += 1
            self.stats.add_removal_reason(
                branduid,
                "missing_celeb_info",
                "관련 셀럽 정보 없음"
            )
            self.logger.debug(f"셀럽 정보 없음으로 제거: {branduid}")
            return False
        
        return True
    
    def _is_discontinued_product(self, product: Dict[str, Any]) -> bool:
        """
        판매종료 상품인지 감지한다.
        
        Args:
            product: 제품 데이터
            
        Returns:
            판매종료 상품 여부
        """
        branduid = product.get("branduid", "unknown")
        
        # 품절 상태 확인
        if product.get("is_soldout", False):
            self.stats.discontinued_products += 1
            self.stats.add_removal_reason(
                branduid,
                "discontinued_product",
                "품절 상태 (is_soldout=True)"
            )
            self.logger.debug(f"품절 상태로 제거: {branduid}")
            return True
        return False
    
    def _clean_and_standardize(self, product: Dict[str, Any]) -> Dict[str, Any]:
        """
        제품 데이터를 정리하고 표준화한다.
        
        Args:
            product: 제품 데이터
            
        Returns:
            정리된 제품 데이터
        """
        cleaned_product = product.copy()
        
        # 문자열 필드 공백 제거 (안전한 처리)
        string_fields = [
            "item_name", "brand_name", "category_name", "color", "material", 
            "origin_country", "manufacturer", "related_celeb", "summary_description"
        ]
        for field in string_fields:
            if field in cleaned_product:
                cleaned_product[field] = safe_strip(cleaned_product[field])
        
        # 가격 필드 정수형 보장
        price_fields = ["price", "origin_price"]
        for field in price_fields:
            if field in cleaned_product:
                try:
                    value = cleaned_product[field]
                    if is_empty_value(value):
                        cleaned_product[field] = 0
                    elif isinstance(value, str):
                        # 문자열에서 숫자만 추출
                        price_numbers = re.findall(r'\d+', value.replace(',', ''))
                        if price_numbers:
                            cleaned_product[field] = int(''.join(price_numbers))
                        else:
                            cleaned_product[field] = 0
                    elif isinstance(value, float) and not math.isnan(value):
                        cleaned_product[field] = int(value)
                    elif isinstance(value, int):
                        cleaned_product[field] = value
                    else:
                        cleaned_product[field] = 0
                except (ValueError, TypeError):
                    cleaned_product[field] = 0
        
        # 불린 필드 보장
        boolean_fields = ["is_discounted", "is_soldout", "is_option_available"]
        for field in boolean_fields:
            if field in cleaned_product:
                cleaned_product[field] = bool(cleaned_product[field])
        
        # 카테고리명 정리 (빈 값인 경우 "기타"로 설정)
        category_name = safe_strip(cleaned_product.get("category_name", ""))
        if not category_name:
            cleaned_product["category_name"] = "기타"
        
        return cleaned_product
    
    def generate_validation_report(self) -> str:
        """
        검증 결과 보고서를 생성한다.
        
        Returns:
            검증 보고서 텍스트
        """
        stats_dict = self.stats.to_dict()
        
        report = []
        report.append("🔍 제품 데이터 검증 보고서")
        report.append("=" * 50)
        report.append("")
        
        # 요약 정보
        summary = stats_dict["summary"]
        report.append("📊 검증 요약:")
        report.append(f"  총 제품 수: {summary['total_products']:,}개")
        report.append(f"  유효 제품 수: {summary['valid_products']:,}개")
        report.append(f"  제거된 제품 수: {summary['removed_products']:,}개")
        report.append(f"  성공률: {summary['success_rate']:.1f}%")
        report.append("")
        
        # 검증 설정 정보
        report.append("⚙️ 검증 설정:")
        report.append(f"  필수 필드: {', '.join(self.required_fields)}")
        report.append(f"  셀럽 정보 필수: {'예' if self.require_celeb_info else '아니오'}")
        report.append("")
        
        # 제거 이유별 통계
        breakdown = stats_dict["removal_breakdown"]
        if summary['removed_products'] > 0:
            report.append("❌ 제거 이유별 통계:")
            report.append(f"  필수 필드 누락: {breakdown['missing_required_fields']}개")
            report.append(f"  유효하지 않은 가격: {breakdown['invalid_price']}개")
            report.append(f"  이미지 누락: {breakdown['missing_images']}개")
            report.append(f"  원산지 정보 누락: {breakdown['missing_origin_country']}개")
            report.append(f"  옵션 정보 불일치: {breakdown['option_inconsistency']}개")
            report.append(f"  판매종료 상품: {breakdown['discontinued_products']}개")
            if self.require_celeb_info:
                report.append(f"  셀럽 정보 누락: {breakdown['missing_celeb_info']}개")
            report.append(f"  중복 branduid: {breakdown['duplicate_branduid']}개")
            report.append("")
        
        # 상세 제거 이유 (최대 10개)
        detailed_reasons = stats_dict["detailed_reasons"][:10]
        if detailed_reasons:
            report.append("📋 제거된 제품 예시 (최대 10개):")
            for reason in detailed_reasons:
                report.append(f"  • {reason['branduid']}: {reason['reason']} - {reason['details']}")
        
        return "\n".join(report)
    
    def save_validation_log(self, file_path: str) -> bool:
        """
        검증 로그를 JSON 파일로 저장한다.
        
        Args:
            file_path: 저장할 파일 경로
            
        Returns:
            저장 성공 여부
        """
        try:
            stats_dict = self.stats.to_dict()
            # 검증 설정 정보도 함께 저장
            stats_dict["validation_config"] = {
                "required_fields": self.required_fields,
                "require_celeb_info": self.require_celeb_info,
                "discontinued_keywords": self.DISCONTINUED_KEYWORDS
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(stats_dict, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"검증 로그 저장 완료: {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"검증 로그 저장 실패: {str(e)}")
            return False
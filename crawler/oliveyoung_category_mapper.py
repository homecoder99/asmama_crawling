"""Oliveyoung 상품 카테고리 감지 및 매핑 로직."""

import re
from typing import Any, Dict
from crawler.utils import convert_country_to_code

class OliveyoungCategoryDetector:
    """상품 카테고리를 자동으로 감지하는 클래스."""

    @staticmethod
    def detect_product_category(product_info: Dict[str, str]) -> str:
        """
        상품 정보를 기반으로 카테고리를 자동 감지한다.
        
        Args:
            product_info: 상품정보제공고시 데이터
            
        Returns:
            감지된 카테고리 ('cosmetics', 'electronics', 'food', 'health_food', 'quasi_drug', 'unknown')
        """
        keys = set(product_info.keys())
        
        # 전자제품 감지 (전자제품 특유 필드들)
        electronics_indicators = {
            "품명 및 모델명", "정격전압, 소비전력", "동일 모델 출시년월", 
            "크기, 무게", "A/S 책임자 / 전화번호"
        }
        if len(keys.intersection(electronics_indicators)) >= 3:
            return "electronics"
        
        # 건강기능식품 감지 (식품보다 더 특수한 필드들)
        health_food_indicators = {
            "영양정보", "기능정보", "섭취량, 섭취방법 및 주의사항 및 부작용 가능성",
            "질병 예방, 치료 의약품 아님 명시", "유전자변형건강기능식품 여부"
        }
        if len(keys.intersection(health_food_indicators)) >= 2:
            return "health_food"
        
        # 식품 감지
        food_indicators = {
            "식품의 유형", "생산자 및 소재지(수입품의 경우 생산자, 수입자 및 제조국)",
            "제조연월일, 소비기한(품질유지기한)", "포장 단위별 내용물의 용량(중량),수량",
            "원재료명 및 함량", "영양성분 표시 대상 여부", "유전자변형식품 여부"
        }
        if len(keys.intersection(food_indicators)) >= 3:
            return "food"
        
        # 의약외품 감지
        if "인증·허가" in keys and "의약외품" in product_info.get("인증·허가", "").lower():
            return "quasi_drug"
        
        # 화장품 감지 (기본 카테고리)
        cosmetics_indicators = {
            "내용물의 용량 또는 중량", "화장품제조업자,화장품책임판매업자 및 맞춤형화장품판매업자",
            "화장품법에 따라 기재해야 하는 모든 성분", "기능성 화장품 식품의약품안전처 심사필 여부"
        }
        if len(keys.intersection(cosmetics_indicators)) >= 2:
            return "cosmetics"
        
        return "unknown"


class OliveyoungCategoryMapper:
    """카테고리별로 상품 정보를 큐텐 필드에 매핑하는 클래스."""

    def __init__(self, logger):
        self.logger = logger

    def map_category_specific_fields(self, product_info: Dict[str, str], product_data: Dict[str, Any], category: str):
        """
        카테고리별로 상품 정보를 큐텐 필드에 매핑한다.
        
        Args:
            product_info: 상품정보제공고시 데이터
            product_data: 결과 데이터 딕셔너리
            category: 감지된 카테고리
        """
        try:
            # 공통 매핑 (모든 카테고리)
            if "제조국" in product_info:
                product_data["origin_country"] = convert_country_to_code(product_info["제조국"])
            
            self.logger.debug(f"product_info.keys(): {product_info.keys()}")

            if category == "cosmetics":
                self._map_cosmetics_fields(product_info, product_data)
            elif category == "electronics":
                self.logger.warning(f"전자제품 카테고리 매핑 시도")
                self._map_electronics_fields(product_info, product_data)
            elif category in ["food", "health_food"]:
                self.logger.warning(f"식품/건강기능식품 카테고리 매핑 시도")
                self._map_food_fields(product_info, product_data)
            elif category == "quasi_drug":
                self.logger.warning(f"의약외품 카테고리 매핑 시도")
                self._map_quasi_drug_fields(product_info, product_data)
            else:
                self.logger.warning(f"알 수 없는 카테고리 매핑 시도")
                self._map_generic_fields(product_info, product_data)
            
            self.logger.debug(f"Oliveyoung 카테고리별 필드 매핑 완료: {category}")
            
        except Exception as e:
            self.logger.warning(f"Oliveyoung 카테고리별 필드 매핑 실패 ({category}): {str(e)}")
            # 매핑 실패시 기본 매핑 시도
            self._map_generic_fields(product_info, product_data)

    def _map_cosmetics_fields(self, product_info: Dict[str, str], product_data: Dict[str, Any]):
        """화장품 카테고리 필드 매핑."""
        others = []

        # 용량/중량
        if "내용물의 용량 또는 중량" in product_info:
            others.append(f"내용물의 용량 또는 중량||*{product_info['내용물의 용량 또는 중량']}")
        
        # 제조업체
        if "화장품제조업자,화장품책임판매업자 및 맞춤형화장품판매업자" in product_info:
            product_data["manufacturer"] = product_info["화장품제조업자,화장품책임판매업자 및 맞춤형화장품판매업자"]
        
        # 사용방법
        if "사용방법" in product_info:
            others.append(f"사용방법||*{product_info['사용방법']}")
        
        # 성분 정보
        if "화장품법에 따라 기재해야 하는 모든 성분" in product_info:
            others.append(f"화장품법에 따라 기재해야 하는 모든 성분||*{product_info['화장품법에 따라 기재해야 하는 모든 성분'].strip()}")
        
        # 제품 사양
        if "제품 주요 사양" in product_info:
            others.append(f"제품 주요 사양||*{product_info['제품 주요 사양']}")

        # 기타 중요 정보를 others 필드에 저장
        important_keys = [k for k in product_info.keys() if product_info[k] and "상세페이지 참조" not in product_info[k]]
        if important_keys:
            other_info = []
            for key in important_keys:
                value = product_info[key]
                other_info.append(f"{key}||*{value}")
            
            if other_info:
                generic_info = "$$".join(other_info)
                if product_data.get("others"):
                    product_data["others"] += f"$${generic_info}"
                else:
                    product_data["others"] = generic_info

        others_info = "$$".join(others)
        if product_data.get("others"):
            product_data["others"] += f"$${others_info}"
        else:
            product_data["others"] = others_info

    def _map_electronics_fields(self, product_info: Dict[str, str], product_data: Dict[str, Any]):
        """전자제품 카테고리 필드 매핑."""
        others = []
        # 제품명
        if "품명 및 모델명" in product_info:
            others.append(f"품명 및 모델명||*{product_info['품명 및 모델명']}")
        
        # 제조업체
        if "제조자" in product_info:
            product_data["manufacturer"] = product_info["제조자"]
        
        # 크기/무게
        if "크기, 무게" in product_info:
            others.append(f"크기, 무게||*{product_info['크기, 무게']}")
        
        # 주요 사양
        if "주요 사양" in product_info:
            others.append(f"주요 사양||*{product_info['주요 사양']}")
        
        # 전력 정보
        if "정격전압, 소비전력" in product_info:
            others.append(f"정격전압, 소비전력||*{product_info['정격전압, 소비전력']}")

        # 기타 중요 정보를 others 필드에 저장
        important_keys = [k for k in product_info.keys() if product_info[k] and "상세페이지 참조" not in product_info[k]]
        if important_keys:
            other_info = []
            for key in important_keys:
                value = product_info[key]
                other_info.append(f"{key}||*{value}")
            
            if other_info:
                generic_info = "$$".join(other_info)
                if product_data.get("others"):
                    product_data["others"] += f"$${generic_info}"
                else:
                    product_data["others"] = generic_info

        others_info = "$$".join(others)
        if product_data.get("others"):
            product_data["others"] += f"$${others_info}"
        else:
            product_data["others"] = others_info

    def _map_food_fields(self, product_info: Dict[str, str], product_data: Dict[str, Any]):
        """식품/건강기능식품 카테고리 필드 매핑."""
        others = []

        # 제품명
        if "제품명" in product_info:
            others.append(f"제품명||*{product_info['제품명']}")
        
        # 제조업체/수입업체
        keys_to_check = [
            "생산자 및 소재지(수입품의 경우 생산자, 수입자 및 제조국)",
            "제조업소의 명칭과 소재지 :수입품의 경우 수입업소명,제조업소명 및 수출국명"
        ]
        for key in keys_to_check:
            if key in product_info:
                product_data["manufacturer"] = product_info[key]
                break
        
        # 중량/용량
        quantity_keys = [
            "포장 단위별 내용물의 용량(중량),수량",
            "내용물의 용량 또는 중량"
        ]
        for key in quantity_keys:
            if key in product_info:
                others.append(f"{key}||*{product_info[key]}")
                break
        
        # 원재료/성분
        if "원재료명 및 함량" in product_info:
            others.append(f"원재료명 및 함량||*{product_info['원재료명 및 함량']}")
        
        # 섭취방법 (건강기능식품의 경우)
        if "섭취량, 섭취방법 및 주의사항 및 부작용 가능성" in product_info:
            others.append(f"섭취량, 섭취방법 및 주의사항 및 부작용 가능성||*{product_info['섭취량, 섭취방법 및 주의사항 및 부작용 가능성']}")
        
        # 기타 중요 정보를 others 필드에 저장
        important_keys = [k for k in product_info.keys() if product_info[k] and "상세페이지 참조" not in product_info[k]]
        if important_keys:
            other_info = []
            for key in important_keys:
                value = product_info[key]
                other_info.append(f"{key}||*{value}")
            
            if other_info:
                generic_info = "$$".join(other_info)
                if product_data.get("others"):
                    product_data["others"] += f"$${generic_info}"
                else:
                    product_data["others"] = generic_info

        others_info = "$$".join(others)
        if product_data.get("others"):
            product_data["others"] += f"$${others_info}"
        else:
            product_data["others"] = others_info

    def _map_quasi_drug_fields(self, product_info: Dict[str, str], product_data: Dict[str, Any]):
        """의약외품 카테고리 필드 매핑."""
        others = []
        # 제품명
        if "품명 및 모델명" in product_info:
            others.append(f"품명 및 모델명||*{product_info['품명 및 모델명']}") 
        
        # 제조업체
        if "제조자" in product_info:
            product_data["manufacturer"] = product_info["제조자"]
        
        # 인증/허가 정보
        if "인증·허가" in product_info:
            others.append(f"인증·허가||*{product_info['인증·허가']}")
        
                # 기타 중요 정보를 others 필드에 저장
        important_keys = [k for k in product_info.keys() if product_info[k] and "상세페이지 참조" not in product_info[k]]
        if important_keys:
            other_info = []
            for key in important_keys:
                value = product_info[key]
                other_info.append(f"{key}||*{value}")
            
            if other_info:
                generic_info = "$$".join(other_info)
                if product_data.get("others"):
                    product_data["others"] += f"$${generic_info}"
                else:
                    product_data["others"] = generic_info

        others_info = "$$".join(others)
        if product_data.get("others"):
            product_data["others"] += f"$${others_info}"
        else:
            product_data["others"] = others_info    

    def _map_generic_fields(self, product_info: Dict[str, str], product_data: Dict[str, Any]):
        """알 수 없는 카테고리의 기본 매핑."""
        others = []
        # 가능한 필드들을 순서대로 매핑 시도
        
        # 제품명 매핑 시도
        name_candidates = ["제품명", "품명 및 모델명", "내용물의 용량 또는 중량"]
        for candidate in name_candidates:
            if candidate in product_info:
                others.append(f"{candidate}||*{product_info[candidate]}")
                break
        
        # 제조업체 매핑 시도  
        manufacturer_candidates = [
            "화장품제조업자,화장품책임판매업자 및 맞춤형화장품판매업자",
            "제조자",
            "생산자 및 소재지(수입품의 경우 생산자, 수입자 및 제조국)"
        ]
        for candidate in manufacturer_candidates:
            if candidate in product_info:
                product_data["manufacturer"] = product_info[candidate]
                break
        
        # 기타 중요 정보를 others 필드에 저장
        important_keys = [k for k in product_info.keys() if product_info[k] and "상세페이지 참조" not in product_info[k]]
        if important_keys:
            other_info = []
            for key in important_keys:
                value = product_info[key]
                other_info.append(f"{key}||*{value}")
            
            if other_info:
                generic_info = "$$".join(other_info)
                if product_data.get("others"):
                    product_data["others"] += f"$${generic_info}"
                else:
                    product_data["others"] = generic_info
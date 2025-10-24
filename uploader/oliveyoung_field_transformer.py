"""Oliveyoung 필드 변환 시스템.

Oliveyoung 크롤링된 상품 데이터를 Qoo10 업로드 형식으로 변환하는 시스템을 구현한다.
번역, 코드 매핑, 가격 산식, Oliveyoung 특화 필드 처리 등을 담당한다.
"""

import re
import json
import csv
from typing import Dict, Any, List, Optional, Tuple
import logging
import openai
import os
from pathlib import Path
from datetime import datetime
import dotenv

try:
    from .data_loader import TemplateLoader
    from .field_transformer import FieldTransformer
    from .brand_translation_manager import BrandTranslationManager
    from .parallel_gpt_processor import ParallelGPTProcessor, TranslationTask
except ImportError:
    from data_loader import TemplateLoader
    from field_transformer import FieldTransformer
    from brand_translation_manager import BrandTranslationManager
    from parallel_gpt_processor import ParallelGPTProcessor, TranslationTask

# 환경변수 로드
dotenv.load_dotenv()

class OliveyoungFieldTransformer(FieldTransformer):
    """
    Oliveyoung 전용 필드 변환 담당 클래스.
    
    기본 FieldTransformer를 상��받아 Oliveyoung 특화 기능을 추가:
    - goods_no 기반 제품 식별
    - 3단계 카테고리 매핑 (category_main > category_sub > category_detail)
    - 할인정보 파싱 (discount_info, benefit_info)
    - 상세정보 파싱 (others 필드의 화장품 정보)
    - 옵션정보 파싱 (복잡한 옵션 구조)
    """
    
    def __init__(self, template_loader: TemplateLoader):
        """
        OliveyoungFieldTransformer 초기화.
        
        Args:
            template_loader: 로딩된 템플릿 데이터
        """
        super().__init__(template_loader)
        self.logger = logging.getLogger(__name__)
        
        # Oliveyoung 특화 매핑 캐시
        self._beauty_category_cache = {}
        self._ingredient_parsing_cache = {}
        
        # 올리브영-Qoo10 카테고리 매핑 로드
        self._olive_qoo_mapping = self._load_olive_qoo_mapping()
        
        # 브랜드 번역 관리자 초기화
        self.brand_manager = BrandTranslationManager()
        
        # 브랜드 매칭 실패 로그용 CSV 파일 경로
        self.failed_brands_csv = Path("output") / f"failed_brands_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.failed_brands_csv.parent.mkdir(exist_ok=True)
        
        # CSV 헤더 작성
        with open(self.failed_brands_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['상품ID', '원본_브랜드명', '영어_번역', '일본어_번역', '실패_시간'])

        # 병렬 처리 프로세서 초기화
        # max_concurrent=50 권장 (4000건 기준 약 4-5분 소요 예상, 1.5일에서 99.8% 단축)
        # Anthropic API는 높은 rate limit을 지원하므로 공격적으로 설정 가능
        # 환경변수로 조절: GPT_MAX_CONCURRENT=100 으로 더 빠르게 가능
        self.parallel_processor = ParallelGPTProcessor(
            max_concurrent=int(os.getenv("GPT_MAX_CONCURRENT", "50")),
            max_retries=3,
            timeout=30.0
        )

        self.logger.info("OliveyoungFieldTransformer 초기화 완료")
        self.logger.info(f"병렬 처리 설정: max_concurrent={self.parallel_processor.max_concurrent}")
    
    def _load_olive_qoo_mapping(self) -> Dict[str, str]:
        """
        올리브영 detail ID와 Qoo10 small code 매핑을 로드한다.
        
        Returns:
            매핑 딕셔너리 {olive_detail_id: qoo_small_code}
        """
        mapping = {}
        mapping_file = os.path.join(os.path.dirname(__file__), "templates", "category", "olive_qoo_mapping.csv")
        
        try:
            with open(mapping_file, 'r', encoding='utf-8-sig') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    olive_detail_id = row['olive_detail_id']
                    qoo_small_code = row['qoo_small_code']
                    if olive_detail_id and qoo_small_code:
                        mapping[olive_detail_id] = qoo_small_code
            
            self.logger.info(f"올리브영-Qoo10 카테고리 매핑 로드 완료: {len(mapping)}개")
            
            return mapping
            
        except Exception as e:
            self.logger.error(f"올리브영-Qoo10 카테고리 매핑 로드 실패: {str(e)}")
            return {}
    
    def transform_products(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Oliveyoung 상품 목록을 Qoo10 형식으로 변환한다 (병렬 GPT 번역 적용).

        Args:
            products: Oliveyoung 크롤링 상품 목록

        Returns:
            변환된 상품 목록
        """
        self.logger.info(f"Oliveyoung 상품 변환 시작: {len(products)}개")
        self.logger.info("🚀 병렬 GPT 처리 사용 - 예상 시간: 4000건 기준 약 4-5분 (기존 1.5일에서 99.8% 단축)")

        # 1단계: 모든 번역 작업 수집
        translation_tasks = []

        for i, product in enumerate(products):
            item_name = str(product.get('item_name', ''))
            brand_name = str(product.get('brand_name', ''))

            # 상품명 번역 작업
            if item_name:
                translation_tasks.append(TranslationTask(
                    index=i,
                    task_type='product_name',
                    input_text=item_name,
                    brand=brand_name
                ))

            # 옵션 번역 작업
            options = product.get('options', [])
            if isinstance(options, str):
                try:
                    options = json.loads(options)
                except:
                    options = options.split('81638') if options else []

            for opt_idx, option in enumerate(options):
                if option and option.strip():
                    translation_tasks.append(TranslationTask(
                        index=i * 10000 + opt_idx,  # 복합 인덱스
                        task_type='option',
                        input_text=option
                    ))

        self.logger.info(f"총 번역 작업 수: {len(translation_tasks)}개 (상품명 + 옵션)")

        # 2단계: 병렬 번역 실행
        import asyncio
        self.logger.info(f"병렬 번역 시작 (동시 처리: {self.parallel_processor.max_concurrent}개)...")
        completed_tasks = asyncio.run(
            self.parallel_processor.process_batch(translation_tasks, show_progress=True)
        )

        # 3단계: 번역 결과를 제품별로 매핑
        product_translations = {}  # {product_index: translated_name}
        option_translations = {}   # {product_index: {option_index: translated_option}}

        for task in completed_tasks:
            if task.task_type == 'product_name':
                product_translations[task.index] = task.result
            elif task.task_type == 'option':
                product_idx = task.index // 10000
                option_idx = task.index % 10000
                if product_idx not in option_translations:
                    option_translations[product_idx] = {}
                option_translations[product_idx][option_idx] = task.result

        self.logger.info("번역 완료! 이제 제품 변환을 시작합니다...")

        # 4단계: 제품 변환 (번역 결과 적용)
        transformed_products = []
        stats = {
            "total": len(products),
            "success": 0,
            "failed": 0,
            "removed_none": 0,
            "removed_missing": 0
        }

        for i, product in enumerate(products):
            try:
                # 번역된 상품명을 product에 임시 저장
                if i in product_translations:
                    product['_translated_item_name'] = product_translations[i]

                # 번역된 옵션을 product에 임시 저장
                if i in option_translations:
                    translated_options = []
                    for opt_idx in sorted(option_translations[i].keys()):
                        translated_opt = option_translations[i][opt_idx]
                        if translated_opt:  # 빈 문자열이 아닌 경우만
                            translated_options.append(translated_opt)
                    product['_translated_options'] = translated_options

                # 제품 변환 (내부에서 _translated_item_name, _translated_options 사용)
                transformed_product = self._transform_single_product(product)
                if transformed_product:
                    transformed_products.append(transformed_product)
                    stats["success"] += 1
                else:
                    stats["failed"] += 1

                if (i + 1) % 100 == 0:
                    self.logger.info(f"변환 진행중: {i+1}/{len(products)}개 완료 (성공: {stats['success']}, 실패: {stats['failed']})")

            except Exception as e:
                stats["failed"] += 1
                self.logger.error(f"상품 변환 실패: {product.get('goods_no', 'unknown')} - {str(e)}")
                continue

        # 최종 통계 로깅
        success_rate = (stats["success"] / stats["total"] * 100) if stats["total"] > 0 else 0
        self.logger.info(f"Oliveyoung 상품 변환 완료:")
        self.logger.info(f"  • 전체: {stats['total']}개")
        self.logger.info(f"  • 성공: {stats['success']}개 ({success_rate:.1f}%)")
        self.logger.info(f"  • 실패: {stats['failed']}개")

        return transformed_products

    
    def _transform_single_product(self, product: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        단일 Oliveyoung 상품을 변환한다.
        
        Args:
            product: Oliveyoung 크롤링 상품 데이터
            
        Returns:
            변환된 상품 데이터 또는 None (변환 실패시)
        """
        try:
            # 기본 정보 추출
            goods_no = str(product.get('goods_no', ''))
            item_name = str(product.get('item_name', ''))
            category_detail_id = str(product.get('category_detail_id', ''))
            brand_name = str(product.get('brand_name', ''))
            price = int(product.get('price', 0))
            
            if not all([goods_no, item_name, category_detail_id, price]):
                self.logger.warning(f"필수 정보 누락: {goods_no}")
                return None
            
            # field_transformer.py와 동일한 구조로 변환
            transformed = {
                # 1. 기본 식별자
                "seller_unique_item_id": product.get("unique_item_id", goods_no),

                # 2. 카테고리 번호
                "category_number": self._get_beauty_category_number(product),

                # 3. 브랜드 번호
                "brand_number": self._get_brand_number(brand_name, goods_no),

                # 4. 상품명 (병렬 번역 결과 우선 사용, 없으면 기존 메서드 호출)
                "item_name": product.get('_translated_item_name') or self._create_product_name_kor_to_jp(item_name, brand_name),
                
                # 5. 상품 상태
                "item_status_Y/N/D": "Y",  # 판매중
                
                # 6. 판매 종료일 (30년 후)
                "end_date": self._get_end_date(),
                
                # 7. 가격 (배송비 추가 + 마진율 적용 + 원 → 엔 환율 적용)
                "price_yen": self._calculate_selling_price(price),
                
                # 8. 수량
                "quantity": 200,
                
                # 9. 메인 이미지
                "image_main_url": product.get("representative_image", ""),
                
                # 10. 추가 이미지들
                "additional_images": product.get("alternative_images", ""),
                
                # 11. HTML 설명 
                "header_html": self._get_header_html(),
                "footer_html": self._get_footer_html(),
                "item_description": self._create_beauty_description_html(product),
                
                # 12. 배송 정보
                "Shipping_number": "771838",  # TracX Logis
                "available_shipping_date": "3",  # 3일 후 배송 가능
                
                # 13. 원산지 정보
                "origin_type": "2",
                "origin_country_id": product.get("origin_country", "KR"),
                
                # 14. 무게
                "item_weight": "1",
                
                # 15. 성인용품 여부
                "under18s_display_Y/N": "N",  # 일반 상품
                
                # 16. 옵션 정보 (일본어 번역)
                "option_info": self._translate_option_info(product.get("option_info", "")),
                
                # 17. 상품 상태
                "item_condition_type": "1"  # 새상품
            }
            
            # 필수 필드 검증 및 None 값 상품 제거
            validation_result = self._validate_transformed_product(transformed, goods_no)
            if not validation_result["is_valid"]:
                return None
            
            return transformed
            
        except Exception as e:
            self.logger.error(f"단일 상품 변환 실패: {str(e)}")
            return None
    
    def _validate_transformed_product(self, transformed: Dict[str, Any], goods_no: str) -> Dict[str, Any]:
        """
        변환된 상품 데이터의 필수 필드를 검증하고 None 값이 있는 경우 로그를 남긴다.
        
        Args:
            transformed: 변환된 상품 데이터
            goods_no: 상품 번호 (로깅용)
            
        Returns:
            검증 결과 딕셔너리 {"is_valid": bool, "missing_fields": list, "none_fields": list}
        """
        # 필수 필드 정의
        required_fields = {
            "seller_unique_item_id": "판매자 고유 상품 ID",
            "category_number": "카테고리 번호", 
            "item_name": "상품명",
            "price_yen": "판매가격"
        }
        
        # 중요 필드 정의 (None이면 경고하지만 제거하지 않음)
        important_fields = {
            "image_main_url": "메인 이미지 URL",
            "item_description": "상품 설명",
            "brand_number": "브랜드 번호"
        }
        
        missing_fields = []
        none_fields = []
        
        # 필수 필드 검증
        for field, description in required_fields.items():
            value = transformed.get(field)
            if value is None:
                none_fields.append(f"{field}({description})")
            elif isinstance(value, str) and not value.strip():
                missing_fields.append(f"{field}({description})")
        
        # 중요 필드 검증 (경고만)
        important_none_fields = []
        for field, description in important_fields.items():
            value = transformed.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                important_none_fields.append(f"{field}({description})")
        
        # 검증 결과 판정
        is_valid = len(none_fields) == 0 and len(missing_fields) == 0
        
        # 로깅
        if not is_valid:
            if none_fields:
                self.logger.warning(f"상품 제거 - None 값 필드: {goods_no} → {', '.join(none_fields)}")
            if missing_fields:
                self.logger.warning(f"상품 제거 - 빈 값 필드: {goods_no} → {', '.join(missing_fields)}")
        elif important_none_fields:
            self.logger.info(f"상품 유지 - 중요 필드 누락: {goods_no} → {', '.join(important_none_fields)}")
        else:
            self.logger.debug(f"상품 검증 통과: {goods_no}")
        
        return {
            "is_valid": is_valid,
            "missing_fields": missing_fields,
            "none_fields": none_fields,
            "important_none_fields": important_none_fields
        }
    
    def _get_beauty_category_number(self, product: Dict[str, Any]) -> Optional[str]:
        """
        Oliveyoung 소분류 ID를 Qoo10 카테고리 번호로 매핑한다.
        
        Args:
            product: 상품 데이터
            
        Returns:
            Qoo10 카테고리 번호 또는 None (매핑 실패시)
        """
        try:
            category_detail_id = product.get('category_detail_id', '')
            
            # 타입 통일: 문자열로 변환
            if isinstance(category_detail_id, (int, float)):
                category_detail_id = str(int(category_detail_id))
            elif not isinstance(category_detail_id, str):
                category_detail_id = str(category_detail_id)
            
            # 매핑 딕셔너리가 비어있는지 확인
            if not self._olive_qoo_mapping:
                self.logger.warning("올리브영-Qoo10 매핑 딕셔너리가 비어있음")
                return None
            
            if category_detail_id and category_detail_id in self._olive_qoo_mapping:
                qoo_code = self._olive_qoo_mapping[category_detail_id]
                self.logger.info(f"소분류 ID 매핑 성공: {category_detail_id} → {qoo_code}")
                return qoo_code
            else:
                self.logger.warning(f"소분류 ID 매핑 실패: '{category_detail_id}' (매핑 파일에 없음)")
                return None
        except Exception as e:
            self.logger.error(f"카테고리 번호 매핑 실패: {str(e)}")
            return None
    
    def _get_brand_number(self, brand_name: str, product_id: str = "") -> str:
        """
        브랜드명에 해당하는 브랜드 번호를 찾는다.
        한국어 브랜드명을 영어/일본어로 번역해서 매칭을 시도한다.
        
        Args:
            brand_name: 브랜드명 (한국어)
            product_id: 상품 ID (CSV 로그용)
            
        Returns:
            브랜드 번호 또는 빈 문자열 (매칭 실패시)
        """
        if not brand_name or not brand_name.strip():
            return ""
            
        try:
            # 1순위: 원본 브랜드명으로 직접 검색
            brand_number = self.template_loader.get_brand_number(brand_name)
            if brand_number:
                self.logger.info(f"브랜드 직접 매칭 성공: {brand_name} → {brand_number}")
                return brand_number
            
            # 2순위: 영어로 번역해서 검색 (파일 캐시 사용)
            english_brand = ""
            try:
                english_brand = self.brand_manager.get_brand_translation(brand_name, "english")
                if english_brand and english_brand.strip():
                    # 번역된 브랜드명 정규화 후 매칭
                    english_brand = english_brand.strip()
                    brand_number = self.template_loader.get_brand_number(english_brand)
                    if brand_number:
                        self.logger.info(f"브랜드 영어 번역 매칭 성공: {brand_name} → {english_brand} → {brand_number}")
                        return brand_number
            except Exception as e:
                self.logger.info(f"브랜드 영어 번역 실패: {brand_name} - {str(e)}")
            
            # 3순위: 일본어로 번역해서 검색 (파일 캐시 사용)
            japanese_brand = ""
            try:
                japanese_brand = self.brand_manager.get_brand_translation(brand_name, "japanese")
                if japanese_brand and japanese_brand.strip():
                    # 번역된 브랜드명 정규화 후 매칭
                    japanese_brand = japanese_brand.strip()
                    brand_number = self.template_loader.get_brand_number(japanese_brand)
                    if brand_number:
                        self.logger.info(f"브랜드 일본어 번역 매칭 성공: {brand_name} → {japanese_brand} → {brand_number}")
                        return brand_number
            except Exception as e:
                self.logger.info(f"브랜드 일본어 번역 실패: {brand_name} - {str(e)}")
            
            # 모든 방법 실패 - 상세 로그 기록 (한국어/영어/일본어 번역본 포함)
            self.logger.warning(f"브랜드 매칭 실패: 원본='{brand_name}' | 영어='{english_brand}' | 일본어='{japanese_brand}'")
            
            # CSV 파일에 실패 기록 저장
            self._save_failed_brand_to_csv(product_id, brand_name, english_brand, japanese_brand)
            
            return ""
            
        except Exception as e:
            self.logger.error(f"브랜드 번호 검색 실패: {brand_name} - {str(e)}")
            return ""
    
    def _save_failed_brand_to_csv(self, product_id: str, brand_name: str, english_brand: str, japanese_brand: str):
        """
        브랜드 매칭 실패 정보를 CSV 파일에 저장한다.
        
        Args:
            product_id: 상품 ID
            brand_name: 원본 브랜드명
            english_brand: 영어 번역
            japanese_brand: 일본어 번역
        """
        try:
            with open(self.failed_brands_csv, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    product_id,
                    brand_name,
                    english_brand,
                    japanese_brand,
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ])
        except Exception as e:
            self.logger.error(f"브랜드 실패 CSV 저장 실패: {str(e)}")
    
    
    def _create_product_name_kor_to_jp(self, kor: str, brand: str) -> str:
        """
        한국어 상품명에서 기획/증정 관련 내용을 제거하고 일본어로 번역하는 함수
        (병렬 처리된 번역 결과를 우선 사용)

        Args:
            kor: 번역할 한국어 상품명
            brand: 브랜드명 (제거 대상)

        Returns:
            정제되고 번역된 일본어 상품명
        """
        if not kor or not kor.strip():
            return ""

        # 병렬 처리로 이미 번역된 경우 (transform_products에서 미리 처리)
        # _transform_single_product에서 호출되므로 product에서 직접 가져옴
        # 이 메서드는 이미 transform_products에서 _translated_item_name로 저장되었음
        # 하지만 여기서는 접근할 수 없으므로, 병렬 번역 결과는 transform_products에서 직접 사용

        # 개별 호출의 경우 기존 로직 유지 (fallback)
        try:
            self.logger.info(f"상품명 개별 번역 (fallback): '{kor}' (브랜드: {brand})")

            response = self.openai_client.responses.create(
                model="gpt-5-mini",
                input=f"""You are a KO→JA e-commerce product-title localizer.

## GOAL
Translate the Korean product name into natural Japanese **product name only**.
- Delete brand names and any promotional or packaging info.
- Output **Japanese only**, a single line, no quotes/brackets/extra words.

## REMOVE (ALWAYS)
1) Brand: remove every appearance of the given brand (and its Japanese/English forms if present).
2) Bracketed segments: delete text inside any of these and the brackets themselves:
   [], ［］, (), （）, {{}}, 「」, 『』, 【】, 〈〉, 《》, <>.
   - If a bracket contains only essential spec like capacity/size/shade (e.g., 50mL, 01, 1.5), keep the info **without brackets**.
3) Promo words (KO): 기획, 증정, 이벤트, 한정, 한정판, 특가, 세트, 1+1, 2+1, 덤, 사은품, 무료, 할인,
   출시, 런칭, 론칭, 신제품, 리뉴얼, 업그레이드, 패키지, 기념, 컬렉션, 에디션, 올리브영,
   단독, 독점, 먼저, 최초, 브랜드명, 픽, 추천, 콜라보, 선택, 단품, 더블, 증량.

## STYLE
- Noun phrase only, no sentence form. No emojis, no decorative symbols.
- Do **not** invent information. If unsure, omit.

## OUTPUT
Return **one line** with the final Japanese product name.
Do not include explanations, quotes, or any non-Japanese text.

--------------------------------
BRAND (to remove): {brand}
KOREAN_NAME: {kor}
"""
            )

            translated = response.output_text.strip()
            self.logger.info(f"상품명 번역 완료: '{kor}' → '{translated}'")
            return translated

        except Exception as e:
            self.logger.error(f"상품명 번역 실패: {kor} (브랜드: {brand}) - {str(e)}")
            return kor  # 실패 시 원문 반환
    
    def _translate_option_value_to_japanese(self, option_value: str) -> str:
        """
        옵션 값을 일본어로 번역한다 (홍보성 키워드 필터링 포함).
        
        Args:
            option_value: 번역할 옵션 값
            
        Returns:
            번역된 일본어 옵션 값
        """
        if not option_value or not option_value.strip():
            return ""
        
        try:
            self.logger.info(f"옵션 값 번역 시작: '{option_value}'")
            
            response = self.openai_client.responses.create(
                model="gpt-5-mini",
                input=f"""You are a KO→JA e-commerce option translator.

## GOAL
Translate the option text into a clean **Japanese option name only** (single line).
- Output **Japanese only** (no Korean). Use katakana for names if needed.
- **Never include price** (e.g., 16,720원).
- **Remove sold-out indicators** (품절/일시품절/재고없음/매진/완판/out of stock) but **translate the rest**.

## WHAT TO KEEP (for option segmentation)
Keep information that defines the option itself:
- **Sale form**: 단품, 세트, ×N개 / N개 세트 / 2개 세트 / 본체+리필 / 50mL+30mL
- **Capacity/size/count**: 120mL, 12g, 3매, 2개, 01/02/003 (숫자 단위와 mL/g/매/개）
- **Type/color/shade/model names**: 00 클리어, 03 로지, 센시비오 H2O 850mL K2
- **Promo that defines composition only** (option-defining): 1+1, 2+1, 증량 +10mL（내용이 구성요소와 명확한 경우）
Do NOT keep marketing claims (인기/No.1/한정기념 등).

## WHAT TO REMOVE
- **Sold-out indicators**: 품절, 일시품절, 재고없음, 매진, 완판, out of stock (remove but translate rest)
- Store codes / metadata: strings like `Option1||*`, `||*0||*200||*...`, `oliveyoung_A...`, SKU/ID hashes
- Bracketed non-structural claims: [ ], ［ ］, ( ), （ ）, 【 】, 〈 〉, 《 》, 「 」, 『 』 **장식문구**。
  ※ 다만、용량 또는 성분（50mL+30mL、본체+리필）**실제 구성**은 남깁니다（괄호는 제거하고 내용만 남깁니다）。
- Any currency or price-like tokens（44,100원, 36,550KRW）

## NORMALIZATION
- Half-width numbers; units as **mL/g**; use **×** for multiplicative counts; use **+** for bundles: `30mL+30mL`, `7mL×3`
- Convert Hangul words to standard JP EC terms: 단품→単品 / 세트→セット / 증정→おまけ / 추가→追가 / 리필→リフィル
- Keep original attribute order **when reasonable**, but ensure readability (spaces between tokens).

## OUTPUT
Return **only** the final Japanese option string on one line.
No explanations, no quotes, no brackets unless part of model numbers (e.g., "01" without brackets).
**If only sold-out indicator remains after processing, return empty string.**

--------------------------------
OPTION_INPUT: {option_value}

# Examples
- IN: `Option2||*03 로지 16,720원` → OUT: `03 ロージー`
- IN: `（품절）센시비오 H2O 850ml K2` → OUT: `센시비오 H2O 850mL K2`
- IN: `품절` → OUT: ``  (empty string - only sold-out indicator)
- IN: `단품 200ml` → OUT: `単品 200mL`
- IN: `30ml+30ml` → OUT: `30mL+30mL`
- IN: `크림 50mL 단품` → OUT: `クリーム 50mL 単品`
- IN: `1+1 50ml` → OUT: `1+1 50mL`
- IN: `본체+리필 12g` → OUT: `本体+リフィル 12g`
- IN: `[품절] 01 베이지` → OUT: `01 ベージュ`
"""
            )
            
            translated = response.output_text.strip()
            self.logger.info(f"옵션 값 번역 완료: '{option_value}' → '{translated}'")
            return translated
            
        except Exception as e:
            self.logger.error(f"옵션 값 번역 실패: {option_value} - {str(e)}")
            # 실패 시 기본 번역 사용
            return self._translate_to_japanese(option_value)
    
    def _get_end_date(self) -> str:
        """
        판매 종료일을 반환한다 (30년 후).
        
        Returns:
            종료일 문자열
        """
        from datetime import datetime
        from dateutil.relativedelta import relativedelta
        end_date = (datetime.now() + relativedelta(years=30)).strftime("%Y-%m-%d")
        return end_date
    
    def _calculate_selling_price(self, price: int) -> int:
        """
        판매가격을 계산한다 (배송비 + 마진율 + 엔화 환율 적용).
        
        Args:
            price: 원본 가격 (원화)
            
        Returns:
            최종 판매가격 (엔화)
        """
        try:
            # 배송비 추가
            shipping_cost = 7500
            price_with_shipping = price + shipping_cost
            
            # 마진율 적용
            margin_rate = 1.0
            price_with_margin = int(price_with_shipping * margin_rate)
            
            # 엔화 환율 적용
            krw_to_jpy_rate = 0.11
            price_jpy_raw = int(price_with_margin * krw_to_jpy_rate)
            
            # 가격 끝자리 보정 (8, 9, 0)
            return self._adjust_price_ending(price_jpy_raw)
            
        except Exception as e:
            self.logger.error(f"가격 계산 실패: {str(e)}")
            return 0
    
    def _adjust_price_ending(self, price: int) -> int:
        """
        가격을 끝자리가 8, 9, 0인 값으로 자동 보정한다.
        
        Args:
            price: 원본 가격
            
        Returns:
            보정된 가격
        """
        rounded_price = round(price)
        last_digit = rounded_price % 10
        
        if last_digit <= 4:
            adjustment = 0  # 0으로 맞춤
        elif last_digit <= 8:
            adjustment = 8  # 8로 맞춤
        else:
            adjustment = 9  # 9로 맞춤
        
        adjusted_price = rounded_price - last_digit + adjustment
        return adjusted_price
    
    def _get_header_html(self) -> str:
        """
        HTML 헤더를 반환한다.
        
        Returns:
            HTML 헤더 문자열
        """
        return '<div style="text-align: center;"><img src="https://lh3.googleusercontent.com/fife/ALs6j_F9ebBomIZsPq9E1S2a_KdQiQ0Ksi1Tqts8FFxXMwlw5VwK1h49yRsUcC9vkMRAEqLg7hK4kRhw-BfB8pJKmCzK0oKUDyOAc4DWjGKI0ek2jN0TODKrVpdinzN_mKKo32RNGAeMm-OaLZSRD6D_RVbRVUxDAWJHaIG8CsOhWM5xYd7amMCd1U2zPXxnyDP11Wt-CFJ2xic29J4fGBpvNE3n3jkzS30U7uoCiTvveeELautGGIWcGMqFqhmeugN6J02QAZcS-8NCWd-XZoWhSA7aRFzkuXP5Gfpn_MrQ9UqXAKS8Bt-l541EPUL0yOcyJb4Eaek_e8dybpfg7vxZhv7zkW_Bf9DBdyZQRZyeBFz417mbILqObBYwRR5iJ9uAqoE3Az8GBOZWoCylOgVkksFh8Tah750Z9V37mmvd-Ze8xDegCK0dP0lzmNYdVltBEyfuDIkauUa2MHx66oCMzyQNfRPpYDYhiIy0X2ZtdZBYcdcUauTzXVgbO2zacve0WRQ8B3gjX0MjSDZz9E2UeAuqjFD2Phf-c0-_To_HvI0SK1HGL-l67MZRtygF--F0_TeetKovzn9B6BRArUUfJCcFrw2mukCh5sB9tkG9zuvXeIGC5U7Rk3kOG-7PgdLTY98H9i79iwBhjYh6EULVPTYMerrIH_MpJ9Vf0_6cDwcMrykHWVV8FPhJc9gkGQpD8LJEd6i9Bq8IuOnHLkRiUpRGYWWEX988uwxxz5tjoetMcyzC2mmZimkXO8uogABHnAEm3ARHvIDAmQTA3K-3g7Vgm1sN7IZcenzU6F7_qWzCY0PTeZLPNBoMyXztrJaAjYH35UT0_Z5Qi3A5GXA43x4gnPzuH1WqMK2XX4A5rP10VaFaho5Mx9jLwlt2y6gNpJu7voBwFOJw7672ePpa5ib4OqTPALrAddw562jtaxwRACzxDWqpXwjma-EgXknQrdF49nh7vpbHATXHmbLnURMWG0d7CQWTf18A3o1gTzmoG6RIbWzGb9FJvhDlq3MSeTrE30DDkbPzC6lGjnDCJaQhqzVOEhy3A0JZ1oXcxGD_vNrHZsPi-EsKUmRjxdg7omlG8HrDBxcvi9nDwfthu10ZvnbONB1iwXj1cjRYCkCFhj4JBE4iZo95GIml_R0VJXdXr0aKOdVH73fYpOLu-D-fPoARAi0eAhwlMp489R0HQhiunzJ0S71xFgN-_Gj8z2Y5OspgEalTA5IJIhZmDoJaACWMJ7OYJmA8Db9OGkFJV6fINXU-as_fQ6bgO7CtYSI4z8ak69pnBn5imXBXSsxanwRQkrY4NJTqDboRHntX02c5IUwWEeBL0wM81bta-aenhx3W4-9LIfkBuOLruOw6BbBcI3ANmZevfY23CVw7-KtfFkhVfZBfnnhRbx4o7g1MQ37s8L6DRsg6ymLn0wjiqSS3krNRYsMtJrMrRGvFyRrslNaRBMSGvFZYW1xyWdSRbTNwTOKpZNCu1JN3HuIpqebKkj64lAgWe3U00NLXZiLFDzBtaah8yOKwBEdhgFMY3__OInnk-g8UuN4k8SYjehuC-8icMSD-AYGId8gRDhpjvMnshdp_Vr7VuZ-hzfaAjjkKoNUVwpUT_AdhVJvufBxpg9Pcbkm2DghB8vU0iMl-laPIEthXtl3sI9g6w1LCfdhab5qG1uBQ5_260Kvj59ZfuhGpF7rI1gg3V57nYHF3wDIvn3mWEIhU_fazqVyIY_s"alt="Image1"/></div>'
    
    def _get_footer_html(self) -> str:
        """
        HTML 푸터를 반환한다.
        
        Returns:
            HTML 푸터 문자열
        """
        return '<div style="text-align: center;"><img src="https://lh3.googleusercontent.com/d/1kaQSPymzMATjoy-wpwYeG-8CN25YnmVK" alt="Image2"><img src="https://lh3.googleusercontent.com/d/1lmdZ3JIuMlIDzJNH40G75U8vrNC4-zKe" alt="Image3"></div>'
    
    def _create_beauty_description_html(self, product: Dict[str, Any]) -> str:
        """
        화장품 상품 정보를 HTML 형식으로 생성한다.
        
        Args:
            product: 상품 데이터
            
        Returns:
            HTML 형식의 상품 정보
        """
        try:
            html_parts = []
            
            # 상품 이미지들 추가
            images = product.get("images", "")
            if images:
                image_urls = [url.strip() for url in images.split("$$") if url.strip()]
                for i, image_url in enumerate(image_urls):
                    html_parts.append(f'<img src="{image_url}" style="max-width:100%;" alt="Image{i+1}">')
            
            return f'<div style="text-align: center;">{"".join(html_parts)}</div>'
            
        except Exception as e:
            self.logger.error(f"화장품 설명 HTML 생성 실패: {str(e)}")
            return ""
    
    def _translate_option_info(self, option_info: str) -> str:
        """
        옵션 정보를 일본어로 번역하고 가격을 엔화로 변환한다.
        
        Args:
            option_info: 원본 옵션 정보 
                        (예: color||*사파이어||*0||*200||*asmama_333540_4$$...)
            
        Returns:
            번역된 옵션 정보 (가격 엔화 변환 포함)
        """
        if not option_info or not option_info.strip():
            return ""
        
        try:
            # $$ 구분자로 각 옵션 분리
            options = option_info.split("$$")
            translated_options = []
            
            for option in options:
                if not option.strip():
                    continue
                
                # ||* 구분자로 분리 (옵션명||*옵션값||*옵션가격||*재고수량||*판매자옵션코드)
                parts = option.split("||*")
                if len(parts) >= 5:
                    option_type = parts[0]  # 옵션 타입 (예: color)
                    option_value = parts[1]  # 옵션 값 (예: 사파이어)
                    option_price = parts[2]  # 옵션 가격 (원화)
                    stock_quantity = parts[3]  # 재고 수량
                    seller_option_code = parts[4]  # 판매자 옵션 코드
                    
                    # 옵션 타입 번역
                    option_type_jp = self._translate_field_name(option_type)
                    
                    # 옵션 값 번역 (홍보성 키워드 필터링)
                    option_value_jp = self._translate_option_value_to_japanese(option_value)
                    
                    # 옵션 가격 변환 (나누기 10만 적용, 마진율 및 환율 제외)
                    try:
                        price_krw = int(option_price) if option_price.isdigit() else 0
                        price_jpy = int(price_krw * 0.11)
                        option_price_jpy = str(price_jpy)
                    except (ValueError, TypeError):
                        option_price_jpy = "0"
                    
                    # 번역된 옵션 재조합
                    translated_option = f"{option_type_jp}||*{option_value_jp}||*{option_price_jpy}||*{stock_quantity}||*{seller_option_code}"
                    translated_options.append(translated_option)
            
            # $$ 구분자로 다시 연결
            return "$$".join(translated_options)
            
        except Exception as e:
            self.logger.error(f"옵션 정보 번역 실패: {option_info} - {str(e)}")
            return option_info  # 실패 시 원본 반환
    
    
    
    def get_transformation_summary(self, input_count: int, output_count: int) -> str:
        """
        변환 작업 요약 정보를 생성한다.
        
        Args:
            input_count: 입력 상품 수
            output_count: 출력 상품 수
            
        Returns:
            변환 요약 문자열
        """
        try:
            summary_lines = []
            summary_lines.append("🔄 Oliveyoung 필드 변환 상세:")
            summary_lines.append(f"  입력 상품: {input_count:,}개")
            summary_lines.append(f"  변환 완료: {output_count:,}개")
            
            if input_count > 0:
                success_rate = (output_count / input_count) * 100
                summary_lines.append(f"  변환 성공률: {success_rate:.1f}%")
            
            if input_count > output_count:
                failed_count = input_count - output_count
                summary_lines.append(f"  제거된 상품: {failed_count:,}개 (None 값 또는 필수 필드 누락)")
            
            summary_lines.append("")
            summary_lines.append("  주요 변환 작업:")
            summary_lines.append("  • goods_no → 제품 식별자 매핑")
            summary_lines.append("  • 3단계 카테고리 → Qoo10 카테고리 매핑")
            summary_lines.append("  • 필수 필드 검증 및 None 값 상품 제거")
            summary_lines.append("  • 할인/혜택 정보 구조화")
            summary_lines.append("  • 화장품 성분/사용법 추출")
            summary_lines.append("  • 복합 옵션 정보 파싱")
            summary_lines.append("  • 배송/반품 정보 구조화")
            
            return "\n".join(summary_lines)
            
        except Exception as e:
            self.logger.error(f"변환 요약 생성 실패: {str(e)}")
            return "변환 요약 생성 실패"
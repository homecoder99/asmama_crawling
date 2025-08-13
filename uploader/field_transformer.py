"""필드 변환 시스템.

크롤링된 상품 데이터를 Qoo10 업로드 형식으로 변환하는 시스템을 구현한다.
번역, 코드 매핑, 가격 산식 등을 처리한다.
"""

import re
from typing import Dict, Any, List, Optional
import logging
import openai
import os
import dotenv
from data_loader import TemplateLoader

# 환경변수 로드
dotenv.load_dotenv()

class FieldTransformer:
    """
    필드 변환 담당 클래스.
    
    크롤링 데이터를 Qoo10 형식으로 변환: 번역, 카테고리 매핑, 브랜드 매핑, 가격 변환 등
    """
    
    def __init__(self, template_loader: TemplateLoader):
        """
        FieldTransformer 초기화.
        
        Args:
            template_loader: 로딩된 템플릿 데이터
        """
        self.logger = logging.getLogger(__name__)
        self.template_loader = template_loader
        
        # OpenAI 클라이언트 초기화 (번역용)
        self.openai_client = openai.OpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # 환율 (원 → 엔)
        self.krw_to_jpy_rate = 0.11  # 1원 = 0.11엔 (약 1100원 = 100엔)
        
        # 배송비 및 마진 설정
        self.shipping_cost = 7500  # 배송비 7500원
        self.margin_rate = 1.0
        
        # 카테고리 매핑 캐시
        self._category_mapping_cache = {}
    
    def _adjust_price_ending(self, price: int) -> int:
        """
        가격을 끝자리가 8, 9, 0인 값으로 자동 보정한다.
        
        엑셀 수식 변환:
        =ROUND(price,0) - MOD(ROUND(price,0),10) + CHOOSE(1+(MOD(ROUND(price,0),10)>4)+(MOD(ROUND(price,0),10)>8), 0,8,9)
        
        Args:
            price: 원본 가격
            
        Returns:
            보정된 가격
        """
        rounded_price = round(price)
        last_digit = rounded_price % 10
        
        # CHOOSE 로직: 끝자리에 따라 0, 8, 9 중 선택
        if last_digit <= 4:
            adjustment = 0  # 0으로 맞춤
        elif last_digit <= 8:
            adjustment = 8  # 8로 맞춤
        else:
            adjustment = 9  # 9로 맞춤
        
        # 끝자리를 제거하고 조정값 추가
        adjusted_price = rounded_price - last_digit + adjustment
        return adjusted_price
        
    def transform_products(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        상품 목록을 Qoo10 형식으로 변환한다.
        
        Args:
            products: 변환할 상품 목록
            
        Returns:
            변환된 상품 목록
        """
        self.logger.info(f"상품 필드 변환 시작: {len(products)}개 상품")
        
        transformed_products = []
        
        for i, product in enumerate(products, 1):
            try:
                branduid = product.get('branduid', 'unknown')
                self.logger.info(f"상품 변환 시작 ({i}/{len(products)}): {branduid}")
                
                transformed_product = self._transform_single_product(product)
                if transformed_product:
                    transformed_products.append(transformed_product)
                    self.logger.info(f"상품 변환 완료 ({i}/{len(products)}): {branduid}")
                else:
                    self.logger.warning(f"상품 변환 실패 - 변환 결과 없음: {branduid}")
            except Exception as e:
                self.logger.error(f"상품 변환 실패: {product.get('branduid', 'unknown')} - {str(e)}")
                continue
        
        self.logger.info(f"상품 필드 변환 완료: {len(transformed_products)}개 성공")
        return transformed_products
    
    def _transform_single_product(self, product: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        단일 상품을 Qoo10 형식으로 변환한다.
        
        Args:
            product: 원본 상품 데이터
            
        Returns:
            변환된 상품 데이터
        """
        transformed = {}
        
        try:
            # 1. 기본 식별자
            transformed["seller_unique_item_id"] = product.get("unique_item_id", "")
            
            # 2. 카테고리 번호 (키워드 매핑)
            category_number = self._get_category_number_by_similarity(product.get("category_name", ""))
            transformed["category_number"] = category_number
            
            # 3. 브랜드 번호
            brand_number = self._get_brand_number(product.get("brand_name", ""))
            transformed["brand_number"] = brand_number
            
            # 4. 상품명 (일본어 번역)
            original_name = (product.get("related_celeb", "") + " " + product.get("item_name", "")).strip()
            self.logger.debug(f"상품명 번역 대상: '{original_name}'")
            item_name_jp = self._translate_to_japanese(original_name)
            transformed["item_name"] = item_name_jp

            # 5. 홍보문구 (일본어 번역)
            summary_desc = product.get("summary_description", "")
            if summary_desc:
                self.logger.debug(f"홍보문구 번역 대상: '{summary_desc[:30]}...'")
                transformed["item_promotion_name"] = self._translate_to_japanese(summary_desc)
            else:
                transformed["item_promotion_name"] = ""
            
            # 6. 상품 상태
            transformed["item_status_Y/N/D"] = "Y"  # 판매중
            
            # 6. 판매 종료일 (30년 후)
            from datetime import datetime
            from dateutil.relativedelta import relativedelta
            end_date = (datetime.now() + relativedelta(years=30)).strftime("%Y-%m-%d")
            transformed["end_date"] = end_date
            
            # 7. 가격 (배송비 추가 + 마진율 적용 + 원 → 엔 환율 적용)
            price_krw = product.get("price", 0)
            if isinstance(price_krw, str):
                price_krw = int(re.sub(r'[^\d]', '', price_krw)) if re.sub(r'[^\d]', '', price_krw) else 0
            
            # 배송비 추가
            price_with_shipping = price_krw + self.shipping_cost
            
            # 마진율 적용
            price_with_margin = int(price_with_shipping * self.margin_rate)
            
            # 엔화 환율 적용
            price_jpy_raw = int(price_with_margin * self.krw_to_jpy_rate)
            
            # 가격 끝자리 보정 (8, 9, 0)
            price_jpy = self._adjust_price_ending(price_jpy_raw)
            transformed["price_yen"] = price_jpy
            self.logger.debug(f"가격 변환: {price_krw:,}원 + 배송비 {self.shipping_cost:,}원 = {price_with_shipping:,}원 × {self.margin_rate} = {price_with_margin:,}원 → {price_jpy_raw:,}엔 → {price_jpy:,}엔 (보정) (환율: {self.krw_to_jpy_rate})")
            
            # 8. 수량 (크롤링 데이터 기준, 없으면 기본값)
            transformed["quantity"] = 200
            
            # 9. 메인 이미지
            rep_image = product.get("representative_image", "")
            transformed["image_main_url"] = rep_image
            self.logger.debug(f"대표 이미지 설정: {rep_image[:50]}{'...' if len(rep_image) > 50 else ''}")
            
            # 10. 추가 이미지들 (서브 이미지)
            alt_images = product.get("alternative_images", "")
            transformed["additional_images"] = alt_images
            if alt_images:
                image_count = len(alt_images.split("$$")) if alt_images else 0
                self.logger.debug(f"추가 이미지 {image_count}개 설정")
            
            # 11. HTML 설명 (상품 정보 + 이미지)
            transformed["header_html"] = '<div style="text-align: center;"><img src="https://lh3.googleusercontent.com/fife/ALs6j_F9ebBomIZsPq9E1S2a_KdQiQ0Ksi1Tqts8FFxXMwlw5VwK1h49yRsUcC9vkMRAEqLg7hK4kRhw-BfB8pJKmCzK0oKUDyOAc4DWjGKI0ek2jN0TODKrVpdinzN_mKKo32RNGAeMm-OaLZSRD6D_RVbRVUxDAWJHaIG8CsOhWM5xYd7amMCd1U2zPXxnyDP11Wt-CFJ2xic29J4fGBpvNE3n3jkzS30U7uoCiTvveeELautGGIWcGMqFqhmeugN6J02QAZcS-8NCWd-XZoWhSA7aRFzkuXP5Gfpn_MrQ9UqXAKS8Bt-l541EPUL0yOcyJb4Eaek_e8dybpfg7vxZhv7zkW_Bf9DBdyZQRZyeBFz417mbILqObBYwRR5iJ9uAqoE3Az8GBOZWoCylOgVkksFh8Tah750Z9V37mmvd-Ze8xDegCK0dP0lzmNYdVltBEyfuDIkauUa2MHx66oCMzyQNfRPpYDYhiIy0X2ZtdZBYcdcUauTzXVgbO2zacve0WRQ8B3gjX0MjSDZz9E2UeAuqjFD2Phf-c0-_To_HvI0SK1HGL-l67MZRtygF--F0_TeetKovzn9B6BRArUUfJCcFrw2mukCh5sB9tkG9zuvXeIGC5U7Rk3kOG-7PgdLTY98H9i79iwBhjYh6EULVPTYMerrIH_MpJ9Vf0_6cDwcMrykHWVV8FPhJc9gkGQpD8LJEd6i9Bq8IuOnHLkRiUpRGYWWEX988uwxxz5tjoetMcyzC2mmZimkXO8uogABHnAEm3ARHvIDAmQTA3K-3g7Vgm1sN7IZcenzU6F7_qWzCY0PTeZLPNBoMyXztrJaAjYH35UT0_Z5Qi3A5GXA43x4gnPzuH1WqMK2XX4A5rP10VaFaho5Mx9jLwlt2y6gNpJu7voBwFOJw7672ePpa5ib4OqTPALrAddw562jtaxwRACzxDWqpXwjma-EgXknQrdF49nh7vpbHATXHmbLnURMWG0d7CQWTf18A3o1gTzmoG6RIbWzGb9FJvhDlq3MSeTrE30DDkbPzC6lGjnDCJaQhqzVOEhy3A0JZ1oXcxGD_vNrHZsPi-EsKUmRjxdg7omlG8HrDBxcvi9nDwfthu10ZvnbONB1iwXj1cjRYCkCFhj4JBE4iZo95GIml_R0VJXdXr0aKOdVH73fYpOLu-D-fPoARAi0eAhwlMp489R0HQhiunzJ0S71xFgN-_Gj8z2Y5OspgEalTA5IJIhZmDoJaACWMJ7OYJmA8Db9OGkFJV6fINXU-as_fQ6bgO7CtYSI4z8ak69pnBn5imXBXSsxanwRQkrY4NJTqDboRHntX02c5IUwWEeBL0wM81bta-aenhx3W4-9LIfkBuOLruOw6BbBcI3ANmZevfY23CVw7-KtfFkhVfZBfnnhRbx4o7g1MQ37s8L6DRsg6ymLn0wjiqSS3krNRYsMtJrMrRGvFyRrslNaRBMSGvFZYW1xyWdSRbTNwTOKpZNCu1JN3HuIpqebKkj64lAgWe3U00NLXZiLFDzBtaah8yOKwBEdhgFMY3__OInnk-g8UuN4k8SYjehuC-8icMSD-AYGId8gRDhpjvMnshdp_Vr7VuZ-hzfaAjjkKoNUVwpUT_AdhVJvufBxpg9Pcbkm2DghB8vU0iMl-laPIEthXtl3sI9g6w1LCfdhab5qG1uBQ5_260Kvj59ZfuhGpF7rI1gg3V57nYHF3wDIvn3mWEIhU_fazqVyIY_s"alt="Image1"/></div>'
            transformed["footer_html"] = '<div style="text-align: center;"><img src="https://lh3.googleusercontent.com/d/1kaQSPymzMATjoy-wpwYeG-8CN25YnmVK" alt="Image2"><img src="https://lh3.googleusercontent.com/d/1lmdZ3JIuMlIDzJNH40G75U8vrNC4-zKe" alt="Image3"></div>'
            
            # 상품 정보 HTML 생성 (일본어 번역)
            product_info_html = self._create_product_info_html(product)
            
            # 상품 이미지들
            images = product.get("images", "")
            image_html = "".join(f'<img src="{image}" style="max-width:100%;" alt="Image{i+4}">' for i, image in enumerate(images.split("$$")) if image.strip())
            
            # 상품 정보 + 이미지 조합 (중간정렬 적용)
            transformed["item_description"] = f'<div style="text-align: center;">{product_info_html}{image_html}</div>'
            
            # 12. 배송 정보
            transformed["Shipping_number"] = "771838" # TracX Logis
            transformed["available_shipping_date"] = "3"  # 3일 후 배송 가능
            
            # 13. 원산지 정보
            transformed["origin_type"] = "2"
            transformed["origin_country_id"] = product.get("origin_country", "")
            
            # 14. 무게
            transformed["item_weight"] = product.get("weight", "")
            
            # 15. 성인용품 여부
            transformed["under18s_display_Y/N"] = "N"  # 일반 상품
            
            # 16. 옵션 정보 (일본어 번역)
            option_info = product.get("option_info", "")
            if option_info:
                transformed["option_info"] = self._translate_option_info(option_info)

            # 17. 상품 상태
            transformed["item_condition_type"] = "1"  # 새상품
            
            return transformed
            
        except Exception as e:
            self.logger.error(f"상품 변환 중 오류: {product.get('branduid', 'unknown')} - {str(e)}")
            return None
    
    def _get_category_number_by_similarity(self, category_name: str) -> Optional[str]:
        """
        키워드 매칭으로 주얼리 카테고리 번호를 찾는다 (AI 사용 안함).
        
        Args:
            category_name: 원본 카테고리명
            
        Returns:
            카테고리 번호 (9자리) 또는 None
        """
        if not category_name or category_name in self._category_mapping_cache:
            return self._category_mapping_cache.get(category_name)
        
        try:
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
            
            # 직접 매칭으로 카테고리 찾기
            if category_name in jewelry_categories:
                category_code = jewelry_categories[category_name]
                self._category_mapping_cache[category_name] = category_code
                self.logger.info(f"카테고리 매핑: '{category_name}' → {category_code}")
                return category_code
            
            # 매칭되지 않으면 None 반환 (product_filter에서 이미 검증됨)
            self.logger.warning(f"카테고리 매핑 실패: '{category_name}' - 키워드 매칭 안됨")
            return None
            
        except Exception as e:
            self.logger.error(f"카테고리 매핑 실패: {category_name} - {str(e)}")
            return None
    
    def _get_brand_number(self, brand_name: str) -> Optional[str]:
        """
        브랜드명에 해당하는 브랜드 번호를 찾는다 (ASMAMA는 고정값 사용).
        
        Args:
            brand_name: 브랜드명
            
        Returns:
            브랜드 번호 또는 None
        """
        # ASMAMA 브랜드는 고정 번호 사용
        if brand_name and "asmama" in brand_name.lower():
            return "112630"
        
        # 다른 브랜드는 템플릿 데이터에서 검색
        return self.template_loader.get_brand_number(brand_name)
    
    def _translate_to_japanese(self, text: str) -> str:
        """
        텍스트를 일본어로 번역한다 (OpenAI GPT-5 사용).
        
        Args:
            text: 번역할 텍스트
            
        Returns:
            번역된 일본어 텍스트
        """
        if not text or not text.strip():
            return ""
        
        try:
            self.logger.info(f"일본어 번역 시작 (OpenAI GPT-5): '{text[:50]}{'...' if len(text) > 50 else ''}'")
            
            response = self.openai_client.responses.create(
                model="gpt-5-mini",
                input=f"""You are a professional Korean-to-Japanese translator specialized in e-commerce product translations. 
Translate the given Korean text to natural Japanese suitable for online shopping product names and descriptions.
Only output the Japanese translation, no explanations or additional text.
Exclude promotional content like events, campaigns, and marketing terms.
If the input is empty or unusual, still attempt translation and never use Korean text as-is.
Use natural Japanese expressions suitable for product listings.

번역할 텍스트: "{text}\""""
            )
            
            translated = response.output_text.strip()
            self.logger.info(f"번역 완료 (OpenAI GPT-5): '{text}' → '{translated}'")
            return translated
            
        except Exception as e:
            self.logger.error(f"OpenAI GPT-5 번역 실패: {text} - {str(e)}")
            return text  # 실패 시 원문 반환
    
    
    def get_transformation_summary(self, original_count: int, transformed_count: int) -> str:
        """
        변환 결과 요약을 생성한다.
        
        Args:
            original_count: 원본 상품 수
            transformed_count: 변환된 상품 수
            
        Returns:
            요약 문자열
        """
        success_rate = (transformed_count / original_count * 100) if original_count > 0 else 0
        
        summary = []
        summary.append("🔄 필드 변환 결과")
        summary.append("=" * 50)
        summary.append("")
        summary.append(f"📊 변환 통계:")
        summary.append(f"  원본 상품 수: {original_count:,}개")
        summary.append(f"  변환 완료: {transformed_count:,}개")
        summary.append(f"  변환 실패: {original_count - transformed_count:,}개")
        summary.append(f"  성공률: {success_rate:.1f}%")
        summary.append("")
        summary.append("🔧 변환 처리:")
        summary.append(f"  배송비: {self.shipping_cost:,}원")
        summary.append(f"  마진율: {self.margin_rate}")
        summary.append(f"  환율 적용: 1원 = {self.krw_to_jpy_rate}엔")
        summary.append(f"  카테고리 매핑: 키워드 매칭")
        summary.append(f"  텍스트 번역: 한국어 → 일본어")
        
        return "\n".join(summary)
    
    def _create_product_info_html(self, product: Dict[str, Any]) -> str:
        """
        상품 정보를 HTML 형식으로 생성한다 (color, material, quantity, size 포함).
        
        Args:
            product: 상품 데이터
            
        Returns:
            HTML 형식의 상품 정보
        """
        try:
            # 상품 정보 필드들 (일본어 번역)
            info_fields = {
                "color": product.get("color", ""),
                "material": product.get("material", ""),
                "quantity": product.get("quantity", ""),
                "size": product.get("size", "")
            }
            
            html_parts = []
            
            for field_name, field_value in info_fields.items():
                if field_value and field_value.strip():
                    # 필드명 일본어 번역
                    field_name_jp = self._translate_field_name(field_name)
                    
                    # 필드값 일본어 번역
                    field_value_jp = self._translate_to_japanese(field_value) if field_value else ""
                    
                    if field_value_jp:
                        html_parts.append(f"<p><strong>{field_name_jp}:</strong> {field_value_jp}</p>")
            
            if html_parts:
                return "<div>" + "".join(html_parts) + "</div>"
            else:
                return ""
                
        except Exception as e:
            self.logger.error(f"상품 정보 HTML 생성 실패: {str(e)}")
            return ""
    
    def _translate_field_name(self, field_name: str) -> str:
        """
        필드명을 일본어로 번역한다.
        
        Args:
            field_name: 영문 필드명
            
        Returns:
            일본어 필드명
        """
        field_translations = {
            "color": "カラー",
            "material": "素材",
            "quantity": "数量",
            "size": "サイズ"
        }
        
        return field_translations.get(field_name, field_name)
    
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
                    
                    # 옵션 값 번역
                    option_value_jp = self._translate_to_japanese(option_value)
                    
                    # 옵션 가격 변환 (나누기 10만 적용, 마진율 및 환율 제외)
                    try:
                        price_krw = int(option_price) if option_price.isdigit() else 0
                        price_jpy = int(price_krw / 10)
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
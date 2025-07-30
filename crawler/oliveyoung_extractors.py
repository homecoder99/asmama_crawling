"""Oliveyoung 상품 데이터 추출 로직."""

import asyncio
import re
from typing import Any, Dict, List
from playwright.async_api import Page
from .utils import clean_text, parse_price


class OliveyoungProductExtractor:
    """Oliveyoung 기본 상품 정보 추출을 담당하는 클래스."""

    def __init__(self, logger):
        self.logger = logger

    async def extract_basic_info(self, page: Page, goods_no: str) -> Dict[str, Any]:
        """기본 상품 정보 추출."""

        product_data = {
            "goods_no": goods_no,
            "item_name": "",
            "brand_name": "",
            "price": 0,
            "origin_price": 0,
            "is_discounted": False,
            "discount_info": "",
            "benefit_info": "",
            "shipping_info": "",
            "refund_info": "",
            "is_soldout": False,
            "images": "",
            "others": "",
            "option_info": "",
            "is_option_available": False,
            "category_main": "",
            "category_sub": "",
            "category_detail": "",
            "category_main_id": "",
            "category_sub_id": "",
            "category_detail_id": "",
            "discount_start_date": "",
            "discount_end_date": "",
            "unique_item_id": f"oliveyoung_{goods_no}",
            "manufacturer": "",
            "origin_country": "",
            "source": "oliveyoung",
            "origin_product_url": f"https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo={goods_no}",
        }

        # 상품명 추출
        await self._extract_product_name(page, product_data)
        
        # 브랜드명 추출
        await self._extract_brand_name(page, product_data)
        
        # 카테고리 추출
        await self._extract_category(page, product_data)
        
        # 품절 상태 판단
        await self._extract_soldout_status(page, product_data)

        return product_data

    async def _extract_product_name(self, page: Page, product_data: Dict[str, Any]):
        """상품명 추출."""
        try:
            name_element = page.locator('.prd_name')
            if await name_element.count() > 0:
                name_text = await name_element.inner_text()
                product_data["item_name"] = clean_text(name_text)
                self.logger.debug(f"Oliveyoung 상품명 추출: {product_data['item_name']}")
            else:
                self.logger.debug("Oliveyoung 상품명(.prd_name)을 찾을 수 없음")
        except Exception as e:
            self.logger.debug(f"Oliveyoung 상품명 추출 실패: {str(e)}")

    async def _extract_brand_name(self, page: Page, product_data: Dict[str, Any]):
        """브랜드명 추출."""
        try:
            brand_element = page.locator('.prd_brand a')
            if await brand_element.count() > 0:
                brand_text = await brand_element.inner_text()
                product_data["brand_name"] = clean_text(brand_text)
                self.logger.debug(f"Oliveyoung 브랜드명 추출: {product_data['brand_name']}")
            else:
                self.logger.debug("Oliveyoung 브랜드명(.prd_brand a)을 찾을 수 없음")
        except Exception as e:
            self.logger.debug(f"Oliveyoung 브랜드명 추출 실패: {str(e)}")

    async def _extract_category(self, page: Page, product_data: Dict[str, Any]):
        """카테고리 정보 추출 (기존 크롤러 방식 유지)."""
        try:
            category_list = []
            category_id_list = []
            
            # 1단계 카테고리: .goods_category1.on이 있는 요소 찾기
            cat1_element = page.locator('.loc_history .goods_category1.on')
            if await cat1_element.count() > 0:
                category_name = clean_text(await cat1_element.inner_text())
                if category_name:
                    category_list.append(category_name)
                    
                    # 상위 li 요소에서 data-ref-dispcatno 추출
                    parent_li = cat1_element.locator('xpath=ancestor::li[@data-ref-dispcatno]').first
                    if await parent_li.count() > 0:
                        category_id = await parent_li.get_attribute('data-ref-dispcatno')
                        category_id_list.append(category_id.strip() if category_id else "")
                    else:
                        category_id_list.append("")
            
            # 2단계 카테고리: .goods_category2.on이 있는 요소 찾기
            cat2_element = page.locator('.loc_history .goods_category2.on')
            if await cat2_element.count() > 0:
                category_name = clean_text(await cat2_element.inner_text())
                if category_name:
                    category_list.append(category_name)
                    
                    # 상위 li 요소에서 data-ref-dispcatno 추출
                    parent_li = cat2_element.locator('xpath=ancestor::li[@data-ref-dispcatno]').first
                    if await parent_li.count() > 0:
                        category_id = await parent_li.get_attribute('data-ref-dispcatno')
                        category_id_list.append(category_id.strip() if category_id else "")
                    else:
                        category_id_list.append("")
            
            # 3단계 카테고리: .goods_category3.on이 있는 요소 찾기
            cat3_element = page.locator('.loc_history .goods_category3.on')
            if await cat3_element.count() > 0:
                category_name = clean_text(await cat3_element.inner_text())
                if category_name:
                    category_list.append(category_name)
                    
                    # 상위 li 요소에서 data-ref-dispcatno 추출
                    parent_li = cat3_element.locator('xpath=ancestor::li[@data-ref-dispcatno]').first
                    if await parent_li.count() > 0:
                        category_id = await parent_li.get_attribute('data-ref-dispcatno')
                        category_id_list.append(category_id.strip() if category_id else "")
                    else:
                        category_id_list.append("")
            
            # 추출된 카테고리를 단계별로 할당
            if len(category_list) >= 1:
                product_data["category_main"] = category_list[0]
                product_data["category_main_id"] = category_id_list[0] if len(category_id_list) >= 1 else ""
            
            if len(category_list) >= 2:
                product_data["category_sub"] = category_list[1] 
                product_data["category_sub_id"] = category_id_list[1] if len(category_id_list) >= 2 else ""
            
            if len(category_list) >= 3:
                product_data["category_detail"] = category_list[2]
                product_data["category_detail_id"] = category_id_list[2] if len(category_id_list) >= 3 else ""
            
            # 전체 카테고리 경로 생성 (category 필드)
            if category_list:
                product_data["category_name"] = " > ".join(category_list)
                self.logger.debug(f"Oliveyoung 카테고리 추출 ({len(category_list)}단계): {product_data['category_name']}")
                self.logger.debug(f"Oliveyoung 카테고리 ID: {category_id_list}")
            else:
                self.logger.debug("Oliveyoung 카테고리 정보를 찾을 수 없음")
                
        except Exception as e:
            self.logger.debug(f"Oliveyoung 카테고리 추출 실패: {str(e)}")

    async def _extract_soldout_status(self, page: Page, product_data: Dict[str, Any]):
        """품절 상태 판단 (.goods_buy 버튼 존재 여부)."""
        try:
            buy_button = page.locator('.goods_buy')
            if await buy_button.count() > 0:
                product_data["is_soldout"] = False
                self.logger.debug("Oliveyoung 판매 중 (구매 버튼 존재)")
            else:
                product_data["is_soldout"] = True
                self.logger.debug("Oliveyoung 품절 (구매 버튼 없음)")
        except Exception as e:
            self.logger.debug(f"Oliveyoung 품절 상태 판단 실패: {str(e)}")
            # 기본값은 판매 중으로 설정
            product_data["is_soldout"] = False


class OliveyoungPriceExtractor:
    """Oliveyoung 가격 정보 추출을 담당하는 클래스."""

    def __init__(self, logger):
        self.logger = logger

    async def extract_price_info(self, page: Page, product_data: Dict[str, Any]):
        """가격 정보 추출."""
        try:
            # 1. 판매가 추출 (필수)
            await self._extract_sale_price(page, product_data)
            
            # 2. 정상가 추출 및 할인 여부 판단
            await self._extract_origin_price(page, product_data)
            
            # 3. 할인 혜택 정보 추출 (할인 시에만)
            if product_data["is_discounted"]:
                await self._extract_discount_info(page, product_data)
                
        except Exception as e:
            self.logger.debug(f"Oliveyoung 가격 정보 추출 실패: {str(e)}")

    async def _extract_sale_price(self, page: Page, product_data: Dict[str, Any]):
        """판매가 추출."""
        price_element = page.locator('.price-2 strong')
        if await price_element.count() > 0:
            price_text = await price_element.inner_text()
            product_data["price"] = parse_price(price_text)
            self.logger.debug(f"Oliveyoung 판매가 추출: {product_data['price']}")
        else:
            self.logger.debug("Oliveyoung 판매가(.price-2 strong)를 찾을 수 없음")

    async def _extract_origin_price(self, page: Page, product_data: Dict[str, Any]):
        """정상가 추출 및 할인 여부 판단."""
        origin_price_element = page.locator('.price-1 strike')
        if await origin_price_element.count() > 0:
            # 할인 중인 경우
            origin_price_text = await origin_price_element.inner_text()
            product_data["origin_price"] = parse_price(origin_price_text)
            product_data["is_discounted"] = True
            self.logger.debug(f"Oliveyoung 정상가 추출 (할인 중): {product_data['origin_price']}")
        else:
            # 할인 없는 경우
            product_data["origin_price"] = product_data["price"]
            product_data["is_discounted"] = False
            self.logger.debug("Oliveyoung 할인 없음 - 정상가와 판매가 동일")

    async def _extract_discount_info(self, page: Page, product_data: Dict[str, Any]):
        """할인 혜택 정보 추출."""
        try:
            discount_items = []
            discount_periods = []
            sale_items = page.locator('#saleLayer .flex-item')
            count = await sale_items.count()
            
            def parse_discount_period(period_text):
                """할인 기간 텍스트를 파싱하여 시작/종료 날짜를 반환"""
                if not period_text:
                    return None, None
                
                # 날짜 패턴 찾기 (YY.MM.DD 형태)
                date_pattern = r'\d{2}\.\d{2}\.\d{2}'
                
                start_date = None
                end_date = None
                
                if '~' in period_text:
                    parts = period_text.split('~')
                    
                    # 시작 날짜 찾기
                    if len(parts) > 0:
                        start_matches = re.findall(date_pattern, parts[0].strip())
                        if start_matches:
                            start_date = start_matches[0]
                    
                    # 종료 날짜 찾기
                    if len(parts) > 1:
                        end_matches = re.findall(date_pattern, parts[1].strip())
                        if end_matches:
                            end_date = end_matches[0]
                else:
                    # ~ 없이 날짜만 있는 경우 - 시작일로 간주 (소진시까지)
                    dates = re.findall(date_pattern, period_text)
                    if dates:
                        start_date = dates[0]
                        # 종료일 없음 (소진시까지)
                
                return start_date, end_date
            
            start_dates = []
            end_dates = []
            
            for i in range(count):
                item = sale_items.nth(i)
                label_element = item.locator('.label')
                price_element = item.locator('.price')
                
                if await label_element.count() > 0 and await price_element.count() > 0:
                    label = clean_text(await label_element.inner_text())
                    price = clean_text(await price_element.inner_text())
                    
                    if label and price:
                        # 할인 기간 파싱 (괄호 안의 날짜 정보)
                        period_match = re.search(r'\(([^)]+)\)', label)
                        if period_match:
                            period = period_match.group(1)
                            discount_periods.append(period)
                            
                            # 시작/종료 날짜 분리
                            start_date, end_date = parse_discount_period(period)
                            if start_date:
                                start_dates.append(start_date)
                            if end_date:
                                end_dates.append(end_date)
                            
                            # 기간 정보를 제외한 할인 이유만 추출
                            discount_reason = re.sub(r'\s*\([^)]+\)', '', label).strip()
                            discount_items.append(f"{discount_reason}||*{price}||*{period}")
                        else:
                            discount_items.append(f"{label}||*{price}")
            
            # FIXME: 할인정보
            if discount_items:
                product_data["discount_info"] = "$$".join(discount_items)
                self.logger.debug(f"Oliveyoung 할인 혜택 정보 추출: {len(discount_items)}개 항목")
                
                # 시작/종료 날짜 저장 (가장 이른 시작일, 가장 늦은 종료일)
                if start_dates:
                    product_data["discount_start_date"] = "$$".join(start_dates)
                    self.logger.debug(f"Oliveyoung 할인 시작일: {product_data['discount_start_date']}")
                
                if end_dates:
                    product_data["discount_end_date"] = "$$".join(end_dates)
                    self.logger.debug(f"Oliveyoung 할인 종료일: {product_data['discount_end_date']}")
                else:
                    self.logger.debug("Oliveyoung 할인 종료일 없음 (소진시까지)")
                    
            else:
                self.logger.debug("Oliveyoung 할인 혜택 정보가 비어있음")
                
        except Exception as e:
            self.logger.debug(f"Oliveyoung 할인 혜택 정보 추출 실패: {str(e)}")


class OliveyoungBenefitExtractor:
    """Oliveyoung 혜택 정보 추출을 담당하는 클래스."""

    def __init__(self, logger):
        self.logger = logger

    async def extract_benefit_info(self, page: Page, product_data: Dict[str, Any]):
        """혜택 정보 추출."""
        # 상품 플래그 정보 추출
        await self._extract_product_flags(page, product_data)
        
        # 결제 혜택 정보 추출
        await self._extract_payment_benefits(page, product_data)

    async def _extract_product_flags(self, page: Page, product_data: Dict[str, Any]):
        """상품 플래그 정보 추출 (세일, 쿠폰, 증정, 오늘드림 등)."""
        try:
            product_flags = ["상품혜택"]
            flag_elements = page.locator('.prd_flag .icon_flag')
            count = await flag_elements.count()
            
            for i in range(count):
                flag_element = flag_elements.nth(i)
                flag_text = clean_text(await flag_element.inner_text())
                if flag_text:
                    product_flags.append(flag_text)
            
            if product_flags:
                # 기존 benefit_info에 플래그 정보 추가
                flag_info = '||*'.join(product_flags)
                if product_data["benefit_info"]:
                    product_data["benefit_info"] += f"$${flag_info}"
                else:
                    product_data["benefit_info"] = flag_info
                self.logger.debug(f"Oliveyoung 상품 플래그 추출: {product_flags}")
            else:
                self.logger.debug("Oliveyoung 상품 플래그 정보를 찾을 수 없음")
                
        except Exception as e:
            self.logger.debug(f"Oliveyoung 상품 플래그 추출 실패: {str(e)}")

    async def _extract_payment_benefits(self, page: Page, product_data: Dict[str, Any]):
        """결제 혜택 정보 추출."""
        try:
            payment_benefits = ["결제혜택"]
            payment_elements = page.locator('.txt_list p')
            count = await payment_elements.count()
            
            for i in range(count):
                benefit_element = payment_elements.nth(i)
                # a 태그 제거하고 텍스트만 추출
                benefit_text = await benefit_element.evaluate('el => el.childNodes[0] ? el.childNodes[0].textContent.trim() : el.textContent.trim()')
                benefit_text = clean_text(benefit_text)
                if benefit_text:
                    payment_benefits.append(benefit_text)
            
            if payment_benefits:
                # 기존 benefit_info에 결제 혜택 정보 추가
                payment_info = '||*'.join(payment_benefits)
                if product_data["benefit_info"]:
                    product_data["benefit_info"] += f"$${payment_info}"
                else:
                    product_data["benefit_info"] = payment_info
                self.logger.debug(f"Oliveyoung 결제 혜택 추출: {payment_benefits}")
            else:
                self.logger.debug("Oliveyoung 결제 혜택 정보를 찾을 수 없음")
                
        except Exception as e:
            self.logger.debug(f"Oliveyoung 결제 혜택 추출 실패: {str(e)}")

class OliveyoungImageExtractor:
    """Oliveyoung 이미지 정보 추출을 담당하는 클래스."""

    def __init__(self, logger):
        self.logger = logger

    async def extract_images(self, page: Page, product_data: Dict[str, Any]):
        """상품 이미지 추출."""
        try:
            image_urls = []
            image_elements = page.locator('.prd_thumb_list img')
            count = await image_elements.count()
            
            for i in range(count):
                img_element = image_elements.nth(i)
                src = await img_element.get_attribute('src')
                if src:
                    # /85/를 /550/로 대체하여 고해상도 이미지 URL 생성
                    high_res_src = src.replace('/85/', '/550/')
                    image_urls.append(high_res_src)
            
            if image_urls:
                # $$ 구분자로 이미지 URL들을 연결
                product_data["images"] = "$$".join(image_urls)
                self.logger.debug(f"Oliveyoung 상품 이미지 추출: {len(image_urls)}개")
            else:
                self.logger.debug("Oliveyoung 상품 이미지를 찾을 수 없음")
                
        except Exception as e:
            self.logger.debug(f"Oliveyoung 상품 이미지 추출 실패: {str(e)}")
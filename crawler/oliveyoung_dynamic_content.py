"""Oliveyoung 동적 콘텐츠 처리 로직."""

import asyncio
from typing import Any, Dict, List
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from .utils import clean_text
from .oliveyoung_category_mapper import OliveyoungCategoryDetector, OliveyoungCategoryMapper


class OliveyoungGiftExtractor:
    """Oliveyoung 증정품 정보 추출을 담당하는 클래스 (동적 로딩)."""

    def __init__(self, logger):
        self.logger = logger

    async def extract_gift_info(self, page: Page, product_data: Dict[str, Any]):
        """증정품 정보 추출 (동적 로딩 필요)."""
        try:
            gift_info_list = []
            
            # 증정품 버튼 찾기
            gift_button = page.locator('.goods_giftinfo')
            
            if await gift_button.count() > 0:
                self.logger.debug("Oliveyoung 증정품 버튼 발견, 클릭 시도")
                
                # 증정품 버튼 클릭
                await gift_button.click()
                
                # 증정품 팝업 로딩 대기
                try:
                    await page.wait_for_selector('.layer_gift_details', timeout=5000)
                    await asyncio.sleep(2)  # 추가 로딩 대기
                    
                    # 증정품 그룹들 추출
                    gift_groups = page.locator('.gifts_detail_group')
                    group_count = await gift_groups.count()
                    
                    for i in range(group_count):
                        group = gift_groups.nth(i)
                        
                        # 품절 여부 확인
                        is_soldout = await group.evaluate('el => el.classList.contains("soldout")')
                        
                        # 증정품 설명
                        desc_element = group.locator('.gifts_desc')
                        if await desc_element.count() > 0:
                            # [소진완료] 플래그 제거하고 설명 추출
                            desc_text = await desc_element.evaluate('''
                                el => {
                                    const flagElement = el.querySelector('.flag');
                                    if (flagElement) flagElement.remove();
                                    return el.textContent.replace(/\\s+/g, ' ').trim();
                                }
                            ''')
                            desc_text = clean_text(desc_text)
                        else:
                            desc_text = ""
                        
                        # 테이블 정보 추출
                        gift_name = ""
                        gift_period = ""
                        gift_target = ""
                        
                        table_rows = group.locator('.layer_tbl_data tr')
                        row_count = await table_rows.count()
                        
                        for j in range(row_count):
                            row = table_rows.nth(j)
                            th_element = row.locator('th')
                            td_element = row.locator('td')
                            
                            if await th_element.count() > 0 and await td_element.count() > 0:
                                header = clean_text(await th_element.inner_text())
                                content = clean_text(await td_element.inner_text())
                                
                                if header == "증정품":
                                    gift_name = content
                                elif header == "증정기간":
                                    gift_period = content
                                elif header == "증정대상":
                                    gift_target = content
                        
                        # 증정품 정보 구성
                        if desc_text or gift_name:
                            gift_status = "[소진완료]" if is_soldout else "[진행중]"
                            gift_info = f"증정품정보||*{gift_status}||*{desc_text}||*{gift_name}||*{gift_period}||*{gift_target}"
                            gift_info_list.append(gift_info.strip())
                    
                    # 팝업 닫기 (다음 크롤링을 위해)
                    close_button = page.locator('.layer_gift_details .layer_close')
                    if await close_button.count() > 0:
                        await close_button.first.click()
                        await asyncio.sleep(1)
                    
                    if gift_info_list:
                        gift_info_text = '$$'.join(gift_info_list)
                        if product_data["benefit_info"]:
                            product_data["benefit_info"] += f"$${gift_info_text}"
                        else:
                            product_data["benefit_info"] = gift_info_text
                        self.logger.debug(f"Oliveyoung 증정품 정보 추출: {len(gift_info_list)}개")
                    else:
                        self.logger.debug("Oliveyoung 증정품 정보가 비어있음")
                        
                except Exception as popup_error:
                    self.logger.debug(f"Oliveyoung 증정품 팝업 처리 실패: {str(popup_error)}")
                    
            else:
                self.logger.debug("Oliveyoung 증정품 버튼을 찾을 수 없음")
                
        except Exception as e:
            self.logger.debug(f"Oliveyoung 증정품 정보 추출 실패: {str(e)}")


class OliveyoungOptionExtractor:
    """Oliveyoung 상품 옵션 정보 추출을 담당하는 클래스 (동적 로딩)."""

    def __init__(self, logger):
        self.logger = logger

    async def extract_option_info(self, page: Page, product_data: Dict[str, Any]):
        """향상된 옵션 정보 추출 (API 응답 모니터링)."""
        try:
            option_button = page.locator('#buyOpt')
            if await option_button.count() == 0:
                if not product_data.get("option_info"):
                    product_data["option_info"] = ""
                return
            
            self.logger.debug("옵션 버튼 클릭 및 API 응답 대기")
            
            # API 응답 리스너 설정
            api_response_data = None
            
            async def handle_response(response):
                nonlocal api_response_data
                if "/getOptInfoListAjax.do" in response.url:
                    self.logger.debug(f"옵션 API 응답: {response.status}")
                    if response.status == 200:
                        try:
                            api_response_data = await response.text()
                        except Exception as e:
                            self.logger.debug(f"옵션 API HTML 파싱 실패: {e}")
                    elif response.status == 403:
                        self.logger.warning("옵션 API 403 Forbidden")
            
            page.on("response", handle_response)
            
            try:
                # 옵션 버튼 클릭
                await option_button.click()
                
                # API 응답 또는 DOM 로딩 대기
                try:
                    await page.wait_for_selector('#option_list li', timeout=8000)
                    await asyncio.sleep(2)
                    
                    # DOM에서 옵션 정보 추출
                    option_items = page.locator('#option_list li')
                    item_count = await option_items.count()
                    
                    if item_count > 0:
                        product_data["is_option_available"] = True
                        option_list = []
                        for i in range(min(item_count, 20)):  # 최대 20개
                            item = option_items.nth(i)
                            option_name_element = item.locator('.option_value')
                            if await option_name_element.count() > 0:
                                option_name = clean_text(await option_name_element.inner_text())
                                if option_name:
                                    # 품절 여부 확인
                                    is_soldout = await item.evaluate('el => el.classList.contains("soldout")')
                                    
                                    # tx_num 클래스에서 옵션 가격 추출
                                    price_element = item.locator('.tx_num')
                                    option_price = 0
                                    if await price_element.count() > 0:
                                        price_text = clean_text(await price_element.inner_text())
                                        # "27,600원" 형태에서 숫자만 추출
                                        import re
                                        price_match = re.search(r'([\d,]+)', price_text)
                                        if price_match:
                                            option_price = int(price_match.group(1).replace(',', ''))
                                    
                                    option_list.append({
                                        "name": option_name,
                                        "price": option_price,
                                        "is_soldout": is_soldout
                                    })
                        
                        if option_list:
                            # 새로운 옵션 형식: 옵션명||*옵션값||*옵션가격||*재고수량||*판매자옵션코드$$
                            formatted_options = []
                            base_price = product_data.get("price", 0)

                            # 1단계: 옵션 개수에 따라 단일/옵션 상품 결정
                            if len(option_list) == 1:
                                product_data["is_option_available"] = False
                                self.logger.info(f"옵션 1개만 존재: 단일 상품으로 변경")
                            else:
                                # 2단계: 가격 검증 - 이상한 가격의 옵션은 품절 처리
                                for idx, option in enumerate(option_list):
                                    option_name = option["name"]
                                    option_price = option["price"]
                                    is_soldout = option["is_soldout"]

                                    # 추가 가격 계산 (옵션 가격 - 기본 판매가)
                                    additional_price = option_price - base_price

                                    # 가격 검증: ±50% 초과 시 삭제
                                    if additional_price < -(base_price * 0.5) or additional_price > base_price * 0.5:
                                        self.logger.warning(f"옵션 가격이 상품 가격 ±50% 초과: {option_name} (추가금액: {additional_price}) - 상품에서 제외")
                                        continue
                                    else:
                                        stock_qty = "0" if is_soldout else "200"  # 품절 상태 반영

                                    unique_item_id = product_data['unique_item_id']

                                    # 3단계: 옵션 포맷팅 (모든 옵션 포함, 이상 가격은 삭제)
                                    formatted_option = f"Option||*{option_name}||*{additional_price}||*{stock_qty}||*{unique_item_id}_{idx+1}$$"
                                    formatted_options.append(formatted_option)

                                product_data["option_info"] = "".join(formatted_options)  # $$ 구분자로 이미 연결됨
                                self.logger.debug(f"옵션 정보 추출 완료: {len(option_list)}개 (가격 검증 포함)")
                        
                except PlaywrightTimeoutError:
                    self.logger.debug("옵션 DOM 로딩 타임아웃")
                    if not product_data.get("option_info"):
                        product_data["option_info"] = ""
                    
                # API 데이터가 있으면 추가 정보로 활용
                if api_response_data:
                    self.logger.debug("옵션 API 데이터 획득 성공")
                    
            finally:
                page.remove_listener("response", handle_response)
                
        except Exception as e:
            self.logger.debug(f"옵션 정보 추출 실패: {e}")
            if not product_data.get("option_info"):
                product_data["option_info"] = ""

class OliveyoungDetailInfoExtractor:
    """Oliveyoung 상품 상세 정보 추출을 담당하는 클래스 (동적 로딩)."""

    def __init__(self, logger):
        self.logger = logger
        self.category_detector = OliveyoungCategoryDetector()
        self.category_mapper = OliveyoungCategoryMapper(logger)
        

    async def extract_detail_info(self, page: Page, product_data: Dict[str, Any]):
        """향상된 상세 정보 추출 및 카테고리별 매핑."""
        try:
            detail_button = page.locator('.goods_buyinfo')
            if await detail_button.count() == 0:
                self.logger.debug("상세정보 버튼을 찾을 수 없음 - 기본 매핑 적용")
                # 버튼이 없어도 카테고리 매핑은 수행
                await self._apply_category_mapping({}, product_data)
                return
            
            self.logger.debug("상세정보 버튼 클릭 및 상품정보제공고시 추출")

            # API 응답 리스너 설정
            api_response_data = None
            
            async def handle_response(response):
                nonlocal api_response_data
                if "/getGoodsArtcAjax.do" in response.url:
                    self.logger.debug(f"상세정보 API 응답: {response.status}")
                    if response.status == 200:
                        try:
                            api_response_data = await response.json()
                        except Exception as e:
                            self.logger.debug(f"상세정보 API JSON 파싱 실패: {e}")
                    elif response.status == 403:
                        self.logger.warning("상세정보 API 403 Forbidden")
            
            page.on("response", handle_response)
            
            try:
                # 상세정보 버튼 클릭
                await detail_button.click()
                
                # DOM 로딩 대기
                try:
                    await page.wait_for_selector('#artcInfo .detail_info_list', timeout=8000)
                    await asyncio.sleep(2)
                    
                    # DOM에서 상품정보제공고시 추출
                    detail_items = page.locator('#artcInfo .detail_info_list')
                    item_count = await detail_items.count()
                    
                    product_info_dict = {}
                    
                    if item_count > 0:
                        for i in range(min(item_count, 15)):  # 최대 15개
                            item = detail_items.nth(i)
                            dt_element = item.locator('dt')
                            dd_element = item.locator('dd')
                            
                            if await dt_element.count() > 0 and await dd_element.count() > 0:
                                key = clean_text(await dt_element.inner_text())
                                value = clean_text(await dd_element.inner_text())
                                if key and value and "상세페이지 참조" not in value:
                                    product_info_dict[key] = value
                        
                        if product_info_dict:
                            self.logger.debug(f"상품정보제공고시 추출 완료: {len(product_info_dict)}개 항목")
                        else:
                            self.logger.debug("유효한 상품정보제공고시를 찾을 수 없음")
                    
                    # 카테고리 감지 및 매핑 적용 
                    await self._apply_category_mapping(product_info_dict, product_data)
                        
                except PlaywrightTimeoutError:
                    self.logger.debug("상세정보 DOM 로딩 타임아웃 - 기본 매핑 적용")
                    await self._apply_category_mapping({}, product_data)
                    
            except Exception as click_error:
                self.logger.debug(f"상세정보 버튼 클릭 실패: {str(click_error)}")
                await self._apply_category_mapping({}, product_data)
                
        except Exception as e:
            self.logger.debug(f"상세정보 추출 실패: {e}")
            await self._apply_category_mapping({}, product_data)
        
        # 정적 배송/반품 정보 추출
        await self._extract_static_additional_info(page, product_data)

    async def _apply_category_mapping(self, product_info_dict: Dict[str, str], product_data: Dict[str, Any]):
        """카테고리 감지 및 필드 매핑 적용."""
        try:
            # 1. 카테고리 감지
            detected_category = self.category_detector.detect_product_category(product_info_dict)
            
            # 2. 카테고리별 필드 매핑
            self.category_mapper.map_category_specific_fields(
                product_info_dict, 
                product_data, 
                detected_category
            )
            
            self.logger.debug(f"카테고리 감지 및 매핑 완료: {detected_category}")
            
        except Exception as e:
            self.logger.warning(f"카테고리 매핑 실패: {str(e)}")

    async def _extract_static_additional_info(self, page: Page, product_data: Dict[str, Any]):
        """정적 배송/반품 정보 추출."""

        # 배송안내 정보
        product_data["shipping_info"] = "일반배송||*2,500원(2만원↑ 무료)||*평균 4일 소요$$오늘드림||*빠름 5,000원·미드나잇 2,500원(3만원↑ 무료)||*당일 도착(마감 20시·13시)"
        
        # 교환/반품 정보
        product_data["refund_info"] = "신청방법||*마이페이지 신청(택배 회수·일부 매장 방문)$$신청기간||*일반 15일 내·하자 3개월/30일 내$$비용||*고객변심: 교환 5,000원·반품 2,500원(도서산간 추가)/매장 방문 무료·하자 시 당사 부담$$불가||*15일 경과·사용/훼손/구성품 누락·고객 과실 등"


class OliveyoungDynamicContentExtractor:
    """Oliveyoung 모든 동적 콘텐츠 추출을 담당하는 통합 클래스."""

    def __init__(self, logger):
        self.logger = logger
        self.gift_extractor = OliveyoungGiftExtractor(logger)
        self.option_extractor = OliveyoungOptionExtractor(logger)
        self.detail_extractor = OliveyoungDetailInfoExtractor(logger)

    async def extract_all_dynamic_content(self, page: Page, product_data: Dict[str, Any]):
        """모든 동적 콘텐츠 추출."""
        # 증정품 정보 추출
        # await self.gift_extractor.extract_gift_info(page, product_data)
        
        # 상품 옵션 정보 추출
        await self.option_extractor.extract_option_info(page, product_data)
        
        # 상품 상세 정보 추출
        await self.detail_extractor.extract_detail_info(page, product_data)
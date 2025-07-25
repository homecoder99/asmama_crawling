"""Asmama 웹사이트 전용 크롤러 구현."""

import asyncio
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
import traceback

from .base import BaseCrawler
from .utils import log_error, parse_price, clean_text, extract_options_from_text, convert_country_to_code, extract_weight_numbers


class AsmamaCrawler(BaseCrawler):
    """
    Asmama 웹사이트 전용 크롤러.
    
    http://www.asmama.com/shop/shopdetail.html?branduid={branduid} 형식의
    URL에서 제품 정보를 크롤링한다.
    """
    
    BASE_URL = "http://www.asmama.com"
    PRODUCT_URL_TEMPLATE = "http://www.asmama.com/shop/shopdetail.html?branduid={branduid}"
    
    def __init__(self, storage: Any = None, max_workers: int = 1):
        """
        Asmama 크롤러를 초기화한다.
        
        Args:
            storage: 데이터 저장소 인스턴스
            max_workers: 최대 동시 세션 수 (서버 부담 경감을 위해 기본값 1)
        """
        super().__init__(storage, max_workers)
        self.semaphore = asyncio.Semaphore(max_workers)  # 동시성 제어
        
        # 지속적인 컨텍스트 및 페이지 관리
        self.persistent_context = None
        self.list_page = None  # 상품 목록 페이지를 계속 열어둘 페이지
    
    async def start(self) -> None:
        """
        크롤러를 시작하고 지속적인 브라우저 컨텍스트를 생성한다.
        """
        await super().start()
        
        # 지속적인 컨텍스트 생성
        self.persistent_context = await self.create_context()
        self.logger.info("지속적인 브라우저 컨텍스트 생성 완료")
    
    async def stop(self) -> None:
        """
        크롤러를 종료하고 지속적인 컨텍스트를 정리한다.
        """
        try:
            # 지속적인 페이지와 컨텍스트 정리
            if self.list_page:
                await self.list_page.close()
                self.list_page = None
                self.logger.info("상품 목록 페이지 닫기 완료")
                
            if self.persistent_context:
                await self.persistent_context.close()
                self.persistent_context = None
                self.logger.info("지속적인 브라우저 컨텍스트 닫기 완료")
        except Exception as e:
            self.logger.error(f"지속적인 리소스 정리 중 오류: {str(e)}")
        
        await super().stop()
        
    async def crawl_single_product(self, branduid: str) -> Optional[Dict[str, Any]]:
        """
        단일 제품을 크롤링한다.
        
        Args:
            branduid: 제품의 branduid
            
        Returns:
            크롤링된 제품 데이터 또는 None (실패 시)
        """
        async with self.semaphore:
            url = self.PRODUCT_URL_TEMPLATE.format(branduid=branduid)
            
            try:
                # 지속적인 컨텍스트에서 새 페이지 생성 (컨텍스트는 닫지 않음)
                if not self.persistent_context:
                    self.persistent_context = await self.create_context()
                
                page = await self.persistent_context.new_page()
                
                # 페이지 로드
                if not await self.safe_goto(page, url):
                    log_error(self.logger, branduid, "페이지 로드 실패", None)
                    await page.close()  # 페이지만 닫기
                    return None
                
                # 제품 데이터 추출
                product_data = await self._extract_product_data(page, branduid)
    
                await page.close()  # 페이지만 닫기 (컨텍스트는 유지)
                
                if product_data:
                    self.logger.info(f"제품 크롤링 성공: {branduid} - {product_data['item_name']}")
                else:
                    log_error(self.logger, branduid, "제품 데이터 추출 실패", None)
                
                return product_data
                
            except Exception as e:
                error_trace = traceback.format_exc()
                log_error(self.logger, branduid, str(e), error_trace)
                return None
    
    async def crawl_from_branduid_list(
        self, 
        branduid_list: List[str],
        batch_size: int = 15
    ) -> List[Dict[str, Any]]:
        """
        branduid 목록에서 여러 제품을 배치 단위로 크롤링한다.
        
        Args:
            branduid_list: branduid 목록
            batch_size: 배치 크기 (서버 부담 경감을 위해 기본값 15)
            
        Returns:
            크롤링된 제품 데이터 목록
        """
        try:
            if not branduid_list:
                self.logger.warning("branduid 목록에서 제품 목록을 찾을 수 없음")
                return []
            
            # 새로운 크롤링 세션 시작 - 기존 저장소 데이터 초기화
            if self.storage:
                self.storage.data = []  # 중복 방지를 위한 내부 데이터 초기화
                self.logger.info("저장소 내부 데이터 초기화 완료")
            
            # branduid 중복 검사 및 제거
            original_count = len(branduid_list)
            branduid_list = list(dict.fromkeys(branduid_list))  # 순서 유지하며 중복 제거
            if len(branduid_list) < original_count:
                removed_count = original_count - len(branduid_list)
                self.logger.info(f"중복된 branduid {removed_count}개 제거: {original_count} → {len(branduid_list)}")
            
            self.logger.info(f"branduid 목록에서 {len(branduid_list)}개 제품 발견 (배치 크기: {batch_size})")
            
            all_products = []
            
            # 배치 단위로 처리
            for i in range(0, len(branduid_list), batch_size):
                batch = branduid_list[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (len(branduid_list) + batch_size - 1) // batch_size
                
                self.logger.info(f"배치 {batch_num}/{total_batches} 처리 중 ({len(batch)}개 제품)")
                
                # 각 제품 크롤링 (순차 처리, max_workers=1)
                tasks = [self.crawl_single_product(branduid) for branduid in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # 성공한 결과만 필터링
                batch_products = [
                    result for result in results 
                    if isinstance(result, dict) and result is not None
                ]
                
                all_products.extend(batch_products)
                self.logger.info(f"배치 {batch_num} 완료: {len(batch_products)}/{len(batch)}개 성공")
                
                # 배치 완료 시마다 Excel 파일로 저장 (원본 데이터)
                if batch_products and self.storage:
                    try:
                        # 현재 배치만 저장 (중복 방지)
                        self.storage.save(batch_products)
                        self.logger.info(f"배치 {batch_num} 데이터 저장 완료 ({len(batch_products)}개 추가, 총 {len(all_products)}개)")
                    except Exception as save_error:
                        self.logger.error(f"배치 {batch_num} 저장 실패: {str(save_error)}")
                
                # 배치 간 휴식 (서버 부담 경감)
                if i + batch_size < len(branduid_list):
                    self.logger.info("다음 배치 처리를 위해 5초 대기 중...")
                    await asyncio.sleep(5)
            
            self.logger.info(f"전체 크롤링 완료: {len(all_products)}/{len(branduid_list)}개 성공")
            return all_products
        
        except Exception as e:
            self.logger.error(f"branduid 목록 크롤링 실패: {str(e)}", exc_info=True)
            return []
        
    async def crawl_branduid_list(
        self, 
        list_url: str, 
        max_items: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        branduid 목록을 크롤링한다.
        
        Args:
            list_url: branduid 목록 페이지 URL
            max_items: 최대 크롤링 아이템 수
            
        Returns:
            크롤링된 branduid 목록
        """
        try:
            # 리스트 페이지에서 branduid 목록 추출
            branduid_list = await self._extract_branduid_list(list_url, max_items)
            
            if not branduid_list:
                self.logger.warning("리스트 페이지에서 branduid 목록을 찾을 수 없음")
                return []
            
            self.logger.info(f"리스트에서 {len(branduid_list)}개 branduid 발견")
            
            return branduid_list
        
        except Exception as e:
            self.logger.error(f"branduid 목록 크롤링 실패: {str(e)}", exc_info=True)
            return []
    
    async def _extract_branduid_list(self, list_url: str, max_items: int) -> List[str]:
        """
        리스트 페이지에서 branduid 목록을 추출한다.
        
        Args:
            list_url: 리스트 페이지 URL
            max_items: 최대 아이템 수
            
        Returns:
            branduid 목록
        """
        try:
            # 지속적인 목록 페이지 생성 또는 재사용
            if not self.list_page:
                if not self.persistent_context:
                    self.persistent_context = await self.create_context()
                
                self.list_page = await self.persistent_context.new_page()
                self.logger.info("상품 목록 페이지 생성 (지속적으로 유지됨)")
            
            # 목록 페이지로 이동 (이미 열려있으면 새로고침)
            if not await self.safe_goto(self.list_page, list_url):
                self.logger.error("목록 페이지 로드 실패")
                return []
            
            # Asmama 베스트셀러 페이지 구조에 맞는 셀렉터 사용
            # df-prl-items 내의 제품 링크에서 branduid 추출
            product_links = await self.list_page.query_selector_all('.df-prl-items .df-prl-item a[href*="shopdetail.html"][href*="branduid="]')
            
            branduid_list = []
            for link in product_links[:max_items]:
                href = await link.get_attribute('href')
                if href and 'branduid=' in href:
                    # branduid 파라미터 추출
                    branduid = href.split('branduid=')[1].split('&')[0]
                    if branduid and branduid not in branduid_list:
                        branduid_list.append(branduid)
                        self.logger.debug(f"branduid 추출: {branduid}")
            
            # 목록 페이지는 닫지 않고 계속 유지
            self.logger.info(f"총 {len(branduid_list)}개 branduid 추출 완료 (목록 페이지 유지됨)")
            return branduid_list
            
        except Exception as e:
            self.logger.error(f"branduid 목록 추출 실패: {str(e)}")
            return []
    
    async def _extract_product_data(self, page, branduid: str) -> Optional[Dict[str, Any]]:
        """
        제품 페이지에서 완전한 데이터 스키마를 추출한다.
        
        추출되는 데이터 필드:
        - color: 제품 색상
        - material: 제품 소재
        - quantity: 수량/구성
        - size: 제품 사이즈
        - weight: 제품 중량
        - unique_item_id: 고유 아이템 ID
        - category_name: 카테고리명
        - brand_name: 브랜드명
        - item_name: 제품명
        - related_celeb: 관련 셀랩 정보
        - origin_price: 원가
        - price: 판매가
        - option_info: 옵션 정보
        - images: 이미지 URL 목록
        - origin_country: 제조국
        - manufacturer: 제조사/판매처
        - benefit_info: 혜택 정보
        - shipping_info: 배송 정보
        - is_discounted: 할인 여부
        - is_soldout: 품절 여부
        - is_option_available: 옵션 선택 가능 여부
        - origin_product_url: 원본 제품 URL
        - source: 데이터 소스
        - others: 기타 정보
        
        Args:
            page: Playwright 페이지 인스턴스
            branduid: 제품 branduid
            
        Returns:
            추출된 제품 데이터 또는 None
        """
        try:
            # 페이지 로딩 대기
            from .utils import random_delay
            await random_delay(1, 3)  # 안티봇 대응 지연

            # 모든 필드를 기본값으로 초기화
            product_data = {
                "branduid": branduid,
                "color": "",
                "material": "",
                "quantity": "",
                "size": "",
                "weight": "",
                "summary_description": "",
                "unique_item_id": "asmama_" + branduid,  # branduid를 unique_item_id로 사용
                "category_name": "",
                "brand_name": "asmama",  # 기본 브랜드명
                "item_name": "",
                "related_celeb": "",
                "origin_price": "",
                "price": "",
                "option_info": "",
                "images": "",
                "origin_country": "",
                "manufacturer": "",
                "benefit_info": "",
                "shipping_info": "",
                "is_discounted": False,
                "is_soldout": False,
                "is_option_available": False,
                "origin_product_url": f"http://www.asmama.com/shop/shopdetail.html?branduid={branduid}",
                "source": "asmama",
                "others": ""
            }

            # 요약 설명 추출 (df-detail-fixed-box)
            try:
                summary_desc = page.locator('div.infoArea div.df-detail-fixed-box div.df-summary-desc')
                if await summary_desc.count() > 0:
                    product_data["summary_description"] = (await summary_desc.inner_text()).strip()
            except Exception as e:
                self.logger.debug(f"요약 설명 추출 실패: {str(e)}")

            # 가격, 적립금, 셀럽 정보 추출 (df-detail-fixed-box > xans-product-detaildesign 테이블)
            try:
                detail_table_rows = page.locator('div.infoArea div.df-detail-fixed-box div.xans-product-detaildesign table tbody tr')
                row_count = await detail_table_rows.count()
                
                for i in range(row_count):
                    row = detail_table_rows.nth(i)
                    th_element = row.locator('th').first
                    td_element = row.locator('td').first
                    
                    if await th_element.count() > 0 and await td_element.count() > 0:
                        th_text = (await th_element.inner_text()).strip()
                        td_text = (await td_element.inner_text()).strip()
                        
                        # 가격 정보 처리
                        if "판매가격" in th_text:
                            # 숫자만 추출
                            price_numbers = ''.join(filter(str.isdigit, td_text))
                            if price_numbers:
                                product_data["price"] = int(price_numbers)
                                product_data["origin_price"] = int(price_numbers)
                        
                        # 할인가격 처리
                        elif "할인" in th_text:
                            discount_numbers = ''.join(filter(str.isdigit, td_text))
                            if discount_numbers:
                                product_data["price"] = int(discount_numbers)
                                product_data["is_discounted"] = True
                        
                        # 적립금 처리
                        elif "적립금" in th_text:
                            product_data["benefit_info"] = td_text
                        
                        # 셀럽 정보 처리
                        elif "CELEB" in th_text:
                            product_data["related_celeb"] = td_text
                            
            except Exception as e:
                self.logger.debug(f"상품 상세 테이블 추출 실패: {str(e)}")

            # 기본 정보 테이블에서 데이터 추출 (df-detail-area > ec-base-table2)
            try:
                base_table_rows = page.locator('div#df-detail-area div.ec-base-table2 table tbody tr')
                row_count = await base_table_rows.count()
                
                if row_count > 0:
                    # 테이블이 있는 경우 기존 로직 사용
                    # 텍스트와 필드명 매핑
                    field_mapping = {
                        "제품명": "item_name",
                        "색상": "color", 
                        "소재": "material",
                        "수량": "quantity",
                        "사이즈": "size",
                        "중량": "weight",
                        "제조국": "origin_country",
                        "판매처": "manufacturer"
                    }
                    
                    for i in range(row_count):
                        row = base_table_rows.nth(i)
                        th_element = row.locator('th').first
                        td_element = row.locator('td').first
                        
                        if await th_element.count() > 0 and await td_element.count() > 0:
                            th_text = (await th_element.inner_text()).strip()
                            td_text = (await td_element.inner_text()).strip()
                            
                            # 텍스트 매칭으로 필드 찾기
                            for key_text, field_name in field_mapping.items():
                                if key_text in th_text:
                                    # 제조국의 경우 국가 코드로 변환
                                    if field_name == "origin_country":
                                        product_data[field_name] = convert_country_to_code(td_text)
                                        self.logger.debug(f"제조국 코드 변환: {td_text} -> {product_data[field_name]}")
                                    # 중량의 경우 숫자만 추출
                                    elif field_name == "weight":
                                        product_data[field_name] = extract_weight_numbers(td_text)
                                        self.logger.debug(f"중량 숫자 추출: {td_text} -> {product_data[field_name]}")
                                    else:
                                        product_data[field_name] = td_text
                                        self.logger.debug(f"추출 성공 ({field_name}): {td_text}")
                                    break
                else:
                    # 테이블이 없는 경우 h2에서 상품명 추출 (fallback)
                    self.logger.debug("기본 정보 테이블이 없음, h2에서 상품명 추출 시도")
                    h2_element = page.locator('div.infoArea div.headingArea h2')
                    if await h2_element.count() > 0:
                        item_name = (await h2_element.inner_text()).strip()
                        if item_name:
                            product_data["item_name"] = item_name
                            self.logger.debug(f"h2에서 상품명 추출 성공: {item_name}")
                                
            except Exception as e:
                self.logger.debug(f"기본 정보 테이블 추출 실패: {str(e)}")
                
                # 예외 발생 시에도 h2에서 상품명 추출 시도
                try:
                    h2_element = page.locator('h2').first
                    if await h2_element.count() > 0:
                        item_name = (await h2_element.inner_text()).strip()
                        if item_name:
                            product_data["item_name"] = item_name
                            self.logger.debug(f"예외 처리 중 h2에서 상품명 추출: {item_name}")
                except Exception as fallback_error:
                    self.logger.debug(f"fallback 상품명 추출도 실패: {str(fallback_error)}")

            # 옵션 정보 추출 (지정된 형식으로 변환)
            try:
                option_list = page.locator('div.infoArea div.df-detail-fixed-box ul.xans-product-option li.xans-product-option')
                select_count = await option_list.count()
                
                if select_count > 0:
                    product_data["is_option_available"] = True
                    option_strings = []
                    
                    for i in range(select_count):
                        select_element = option_list.nth(i).locator('select[name*="optionlist"]')
                        
                        # 옵션명 추출 (label 속성에서)
                        option_name = await select_element.get_attribute('label') or f"옵션{i+1}"
                        
                        # 옵션값들 추출 - value가 빈 문자열이 아닌 것들
                        options = await select_element.locator('option').all()
                        
                        for option in options:
                            option_text = (await option.inner_text()).strip()
                            if option_text and option_text != "옵션 선택" and (await option.get_attribute('sto_state') == "SALE"):
                                option_value = await option.get_attribute('value')
                                if not option_value or option_value == "":
                                    continue
                                
                                # 가격 정보 추출
                                price_attr = await option.get_attribute('org_opt_price')
                                stock_attr = "200"
                                sto_id = product_data["unique_item_id"] + "_" + await option.get_attribute('sto_id') or "0"
                                
                                # 형식: 옵션명||*옵션값||*옵션가격||*재고수량||*판매자옵션코드$$
                                option_string = f"{option_name}||*{option_text}||*{price_attr}||*{stock_attr}||*{sto_id}"
                                option_strings.append(option_string)
                                
                    # $$ 구분자로 연결
                    if option_strings:
                        product_data["option_info"] = "$$".join(option_strings)
                    else:
                        product_data["is_option_available"] = False
                        
            except Exception as e:
                self.logger.debug(f"옵션 정보 추출 실패: {str(e)}")

            # 구매 버튼으로 품절 상태 확인
            try:
                buy_button = page.locator('div.infoArea div.df-detail-fixed-box div.xans-product-action .btn.buy').first
                if await buy_button.count() == 0:
                    # 버튼이 없으면 품절
                    # FIXME: 실제 검증 필요
                    product_data["is_soldout"] = True
                    
            except Exception as e:
                self.logger.debug(f"구매 버튼 분석 실패: {str(e)}")
            
            # 카테고리 분류 (상품명 기반)
            try:
                item_name = product_data.get("item_name", "").lower()
                
                # 카테고리 키워드 매핑
                category_mapping = {
                    "팔찌": ["팔찌"],
                    "귀찌": ["귀찌", "피어싱", "피어스"],
                    "귀걸이": ["귀걸이", "이어링", "입찌", "이어커프"],
                    "반지": ["반지", "링"],
                    "목걸이": ["목걸이", "체인", "펜던트"],
                    "헤어핀": ["헤어핀", "집게핀", "헤어후크", "헤어비녀"],
                    "헤어밴드": ["헤어밴드", "머리띠"],
                    "헤어끈": ["헤어끈", "포니테일", "스크런치"]
                }
                
                # 키워드 매칭으로 카테고리 분류
                matched_category = ""
                for category, keywords in category_mapping.items():
                    for keyword in keywords:
                        if keyword in item_name:
                            matched_category = category
                            break
                    if matched_category:
                        break
                
                product_data["category_name"] = matched_category
                self.logger.debug(f"카테고리 분류: {item_name} -> {matched_category}")
                
            except Exception as e:
                self.logger.debug(f"카테고리 분류 실패: {str(e)}")

            # 배송/결제/반품 정보 추출 (detail-guide)
            try:
                guide_sections = page.locator('div.detail-guide div.section')
                section_count = await guide_sections.count()
                
                others_info = {}
                
                for i in range(section_count):
                    section = guide_sections.nth(i)
                    
                    # 섹션 제목 추출
                    title_element = section.locator('h3').first
                    content_element = section.locator('div.df-cont').first
                    
                    if await title_element.count() > 0 and await content_element.count() > 0:
                        title_text = (await title_element.inner_text()).strip()
                        content_text = (await content_element.inner_text()).strip()
                        
                        # 배송정보 처리
                        if "배송정보" in title_text:
                            # 배송비, 기간, 택배사 추출
                            shipping_parts = []
                            
                            # 택배사 추출
                            if "CJ 대한통운" in content_text:
                                shipping_parts.append("택배사: CJ 대한통운")
                            
                            # 배송료 추출
                            if "배송료" in content_text:
                                lines = content_text.split('\n')
                                for line in lines:
                                    if "배송료" in line:
                                        shipping_parts.append(line.strip())
                                        break
                            
                            # 배송기간 추출
                            if "배송기간" in content_text:
                                lines = content_text.split('\n')
                                for line in lines:
                                    if "배송기간" in line:
                                        shipping_parts.append(line.strip())
                                        break
                            
                            product_data["shipping_info"] = " | ".join(shipping_parts)
                            
                        # 결제정보와 반품정보는 others에 저장
                        elif "결제정보" in title_text:
                            others_info["payment_info"] = content_text
                        elif "반품" in title_text or "교환" in title_text:
                            others_info["return_info"] = content_text
                
                # others 필드에 추가 정보 저장 (텍스트 형식)
                if others_info:
                    others_text = []
                    for key, value in others_info.items():
                        if key == "payment_info":
                            others_text.append(f"[결제정보] {value}")
                        elif key == "return_info":
                            others_text.append(f"[교환/반품정보] {value}")
                    product_data["others"] = " | ".join(others_text)
                    
            except Exception as e:
                self.logger.debug(f"상세 가이드 정보 추출 실패: {str(e)}")

            # 이미지 URL 추출
            try:
                image_urls = ""
                
                # 1. 썸네일 이미지 추출 (imgArea)
                thumbnail_img = page.locator('div.imgArea div.keyImg div.thumbnail span.detail-image img.detail_image').first
                if await thumbnail_img.count() > 0:
                    thumbnail_src = await thumbnail_img.get_attribute('src')
                    if thumbnail_src:
                        # 상대경로를 절대경로로 변환
                        if thumbnail_src.startswith('/'):
                            thumbnail_src = f"http://www.asmama.com{thumbnail_src}"
                        image_urls += thumbnail_src
                        self.logger.debug(f"썸네일 이미지 추출: {thumbnail_src}")
                
                # 2. 상세 이미지들 추출 (상품상세페이지 본문)
                detail_imgs = page.locator('div#df-detail-area div.cont img[src*="asmamaybs.openhost.cafe24.com"]')
                detail_count = await detail_imgs.count()
                
                for i in range(detail_count):
                    img = detail_imgs.nth(i)
                    img_src = await img.get_attribute('src')
                    if img_src and img_src not in image_urls:
                        image_urls += "$$" + img_src
                        self.logger.debug(f"상세 이미지 추출: {img_src}")
                
                product_data["images"] = image_urls
                self.logger.debug(f"총 {len(image_urls)}개 이미지 추출 완료")
                
            except Exception as e:
                self.logger.debug(f"이미지 URL 추출 실패: {str(e)}")
            
            return product_data
            
        except Exception as e:
            self.logger.error(f"제품 데이터 추출 실패 ({branduid}): {str(e)}")
            return None
    
    def crawl(self, branduid_list: List[str]) -> List[Dict[str, Any]]:
        """
        동기 방식으로 여러 제품을 크롤링한다.
        
        Args:
            branduid_list: 크롤링할 branduid 목록
            
        Returns:
            크롤링된 제품 데이터 목록
        """
        async def _async_crawl():
            async with self:
                tasks = [self.crawl_single_product(branduid) for branduid in branduid_list]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                products = [
                    result for result in results 
                    if isinstance(result, dict) and result is not None
                ]
                
                return products
        
        return asyncio.run(_async_crawl())
"""
올리브영 3단계 카테고리 구조 완전 추출 테스트 코드.

1단계: 메인 페이지에서 대분류, 중분류 추출
2단계: 각 중분류 페이지에서 소분류 추출
3단계: CSV로 저장
"""

import asyncio
import csv
import logging
from typing import List, Dict, Any
from crawler.oliveyoung import OliveyoungCrawler
from crawler.storage import JSONStorage
import os

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class OliveyoungFullCategoryExtractor:
    """
    올리브영 완전한 3단계 카테고리 구조 추출 클래스.
    """
    
    def __init__(self):
        """추출기 초기화."""
        self.logger = logging.getLogger(__name__)
        
        # CSV 컬럼 정의
        self.csv_columns = [
            'category_main',
            'category_main_id',
            'category_sub', 
            'category_sub_id',
            'category_detail',
            'category_detail_id'
        ]
        
        # 출력 파일 경로
        self.output_dir = "output"
        self.csv_file = os.path.join(self.output_dir, "oliveyoung_full_categories.csv")
        
        # 출력 디렉토리 생성
        os.makedirs(self.output_dir, exist_ok=True)
        
        # URL 템플릿
        self.CATEGORY_URL_TEMPLATE = "https://www.oliveyoung.co.kr/store/display/getMCategoryList.do?dispCatNo={categoryId}"
        
    def categorize_by_hierarchy(self, categories: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
        """
        카테고리를 계층별로 분류한다.
        
        올리브영 카테고리 ID 구조:
        - 대분류: 11자리 (예: 10000010012)
        - 중분류: 15자리 (예: 100000100120007)
        - 소분류: 19자리 (예: 1000001001200070001)
        
        Args:
            categories: 모든 카테고리 목록
            
        Returns:
            계층별로 분류된 카테고리 딕셔너리
        """
        main_categories = []   # 대분류 (11자리)
        sub_categories = []    # 중분류 (15자리)
        detail_categories = [] # 소분류 (19자리)
        
        for category in categories:
            cat_id = category['id']
            
            if len(cat_id) == 11:
                main_categories.append(category)
            elif len(cat_id) == 15:
                sub_categories.append(category)
            elif len(cat_id) == 19:
                detail_categories.append(category)
        
        self.logger.info(f"카테고리 분류 완료: 대분류 {len(main_categories)}개, 중분류 {len(sub_categories)}개, 소분류 {len(detail_categories)}개")
        
        return {
            'main': main_categories,
            'sub': sub_categories,
            'detail': detail_categories
        }
    
    def build_category_hierarchy(self, categorized: Dict[str, List[Dict[str, str]]]) -> Dict[str, Dict[str, Any]]:
        """
        카테고리 계층 구조를 빌드한다.
        
        올리브영 카테고리 계층 매칭:
        - 중분류 15자리는 대분류 11자리로 시작
        - 소분류 19자리는 중분류 15자리로 시작
        
        Args:
            categorized: 계층별로 분류된 카테고리
            
        Returns:
            계층 구조 딕셔너리
        """
        hierarchy = {}
        
        # 대분류를 기준으로 구조 생성
        for main_cat in categorized['main']:
            main_id = main_cat['id']  # 11자리
            main_name = main_cat['name']
            
            hierarchy[main_id] = {
                'name': main_name,
                'id': main_id,
                'type': 'main',
                'sub_categories': {}
            }
            
            # 해당 대분류에 속하는 중분류 찾기 (15자리가 11자리로 시작)
            for sub_cat in categorized['sub']:
                sub_id = sub_cat['id']  # 15자리
                if sub_id.startswith(main_id):  # 15자리가 11자리로 시작하는지 확인
                    hierarchy[main_id]['sub_categories'][sub_id] = {
                        'name': sub_cat['name'],
                        'id': sub_id,
                        'type': 'sub',
                        'detail_categories': {}
                    }
                    
                    # 해당 중분류에 속하는 소분류 찾기 (메인 페이지에서 추출된 것만)
                    for detail_cat in categorized['detail']:
                        detail_id = detail_cat['id']  # 19자리
                        if detail_id.startswith(sub_id):  # 19자리가 15자리로 시작하는지 확인
                            hierarchy[main_id]['sub_categories'][sub_id]['detail_categories'][detail_id] = {
                                'name': detail_cat['name'],
                                'id': detail_id,
                                'type': 'detail'
                            }
        
        return hierarchy
    
    def build_category_hierarchy_new(self, categories: Dict[str, List[Dict[str, str]]]) -> Dict[str, Dict[str, Any]]:
        """
        새로운 방식으로 카테고리 계층 구조를 빌드한다.
        
        Args:
            categories: 메인 페이지에서 추출된 카테고리 (main, sub)
            
        Returns:
            계층 구조 딕셔너리
        """
        hierarchy = {}
        
        # 대분류를 기준으로 구조 생성
        for main_cat in categories['main']:
            main_id = main_cat['id']  # 11자리
            main_name = main_cat['name']
            
            hierarchy[main_id] = {
                'name': main_name,
                'id': main_id,
                'type': 'main',
                'sub_categories': {}
            }
            
            # 해당 대분류에 속하는 중분류 찾기
            for sub_cat in categories['sub']:
                sub_id = sub_cat['id']  # 15자리
                if sub_id.startswith(main_id):  # 15자리가 11자리로 시작하는지 확인
                    hierarchy[main_id]['sub_categories'][sub_id] = {
                        'name': sub_cat['name'],
                        'id': sub_id,
                        'type': 'sub',
                        'detail_categories': {}
                    }
        
        self.logger.info(f"계층 구조 빌드 완료: 대분류 {len(hierarchy)}개")
        return hierarchy
    
    async def extract_sub_category_details(self, crawler: OliveyoungCrawler, sub_category_id: str) -> List[Dict[str, str]]:
        """
        중분류 페이지에서 소분류 목록을 추출한다.
        
        Args:
            crawler: 올리브영 크롤러 인스턴스
            sub_category_id: 중분류 카테고리 ID
            
        Returns:
            소분류 목록
        """
        try:
            # 중분류 페이지 URL 생성
            category_url = self.CATEGORY_URL_TEMPLATE.format(categoryId=sub_category_id)
            
            # 새 페이지 생성
            page = await crawler.crawl_context.new_page()
            
            try:
                self.logger.info(f"중분류 페이지 이동: {category_url}")
                
                # 페이지 로드
                if not await crawler.safe_goto(page, category_url):
                    self.logger.error(f"중분류 페이지 로드 실패: {sub_category_id}")
                    return []
                
                # 페이지 로딩 대기
                from crawler.utils import random_delay
                await random_delay(2, 3)
                
                # 소분류 추출 - ul.cate_list_box 내의 a 태그들
                detail_categories = []
                
                # CSS 선택자로 소분류 링크들 찾기
                category_links = page.locator('ul.cate_list_box li a')
                link_count = await category_links.count()
                
                self.logger.info(f"중분류 {sub_category_id}에서 {link_count}개 소분류 링크 발견")
                
                for i in range(link_count):
                    try:
                        link = category_links.nth(i)
                        
                        # class 속성에서 카테고리 ID 추출
                        class_attr = await link.get_attribute('class')
                        category_name = await link.inner_text()
                        
                        if class_attr and category_name:
                            category_name = category_name.strip()
                            class_attr = class_attr.strip()
                            
                            # 숫자로만 구성된 클래스명이 카테고리 ID (19자리 소분류)
                            if class_attr.isdigit() and len(class_attr) == 19 and category_name != '전체':
                                detail_categories.append({
                                    'id': class_attr,
                                    'name': category_name
                                })
                                self.logger.debug(f"소분류 추가: {class_attr} - {category_name}")
                    
                    except Exception as e:
                        self.logger.debug(f"소분류 링크 {i} 처리 중 오류: {e}")
                        continue
                
                self.logger.info(f"중분류 {sub_category_id}에서 {len(detail_categories)}개 소분류 추출 완료")
                return detail_categories
                
            finally:
                await page.close()
                
        except Exception as e:
            self.logger.error(f"중분류 {sub_category_id} 소분류 추출 실패: {str(e)}")
            return []
    
    async def extract_categories_from_main_page(self, crawler: OliveyoungCrawler) -> Dict[str, List[Dict[str, str]]]:
        """
        메인 페이지에서 대분류와 중분류를 추출한다.
        
        Args:
            crawler: 올리브영 크롤러 인스턴스
            
        Returns:
            계층별로 분류된 카테고리 딕셔너리
        """
        try:
            # 컨텍스트 확인
            if not crawler.crawl_context:
                try:
                    crawler.crawl_context = await crawler.cookie_manager.ensure_context()
                except Exception as e:
                    self.logger.error(f"크롤링 컨텍스트 생성 실패: {e}")
                    return {"main": [], "sub": []}
            
            # 메인 페이지 전용 페이지 생성
            main_page = await crawler.crawl_context.new_page()
            
            try:
                self.logger.info(f"메인 페이지로 이동: {crawler.MAIN_PAGE_URL}")
                
                if not await crawler.safe_goto(main_page, crawler.MAIN_PAGE_URL):
                    self.logger.error("메인 페이지 로드 실패")
                    return {"main": [], "sub": []}
                
                # 페이지 로딩 대기
                from crawler.utils import random_delay
                await random_delay(3, 5)
                
                # 대분류 추출: p.sub_depth > a[data-ref-dispcatno]
                main_category_selector = '#gnbAllMenu .all_menu_wrap .sub_menu_box .sub_depth > a[data-ref-dispcatno]'
                main_category_elements = main_page.locator(main_category_selector)
                main_count = await main_category_elements.count()
                
                # 중분류 추출: ul > li > a[data-ref-dispcatno]
                sub_category_selector = '#gnbAllMenu .all_menu_wrap .sub_menu_box ul > li > a[data-ref-dispcatno]'
                sub_category_elements = main_page.locator(sub_category_selector)
                sub_count = await sub_category_elements.count()
                
                self.logger.info(f"카테고리 링크 발견: 대분류 {main_count}개, 중분류 {sub_count}개")
                
                main_categories = []
                sub_categories = []
                
                # 대분류 처리 (11자리)
                for i in range(main_count):
                    try:
                        element = main_category_elements.nth(i)
                        cat_id = await element.get_attribute('data-ref-dispcatno')
                        cat_name = await element.inner_text()
                        
                        if cat_id and cat_name and cat_id.strip() and cat_name.strip():
                            cat_id = cat_id.strip()
                            cat_name = cat_name.strip()
                            
                            # 11자리 대분류 ID만 추출
                            if cat_id.isdigit() and len(cat_id) == 11:
                                main_categories.append({
                                    "id": cat_id,
                                    "name": cat_name
                                })
                                self.logger.debug(f"대분류 추가: {cat_id} - {cat_name}")
                    
                    except Exception as e:
                        self.logger.debug(f"대분류 요소 {i} 처리 중 오류: {e}")
                        continue
                
                # 중분류 처리 (15자리)
                for i in range(sub_count):
                    try:
                        element = sub_category_elements.nth(i)
                        cat_id = await element.get_attribute('data-ref-dispcatno')
                        cat_name = await element.inner_text()
                        
                        if cat_id and cat_name and cat_id.strip() and cat_name.strip():
                            cat_id = cat_id.strip()
                            cat_name = cat_name.strip()
                            
                            # 15자리 중분류 ID만 추출
                            if cat_id.isdigit() and len(cat_id) == 15:
                                sub_categories.append({
                                    "id": cat_id,
                                    "name": cat_name
                                })
                                self.logger.debug(f"중분류 추가: {cat_id} - {cat_name}")
                    
                    except Exception as e:
                        self.logger.debug(f"중분류 요소 {i} 처리 중 오류: {e}")
                        continue
                
                self.logger.info(f"카테고리 추출 완료: 대분류 {len(main_categories)}개, 중분류 {len(sub_categories)}개")
                
                return {
                    "main": main_categories,
                    "sub": sub_categories
                }
                
            finally:
                await main_page.close()
                
        except Exception as e:
            self.logger.error(f"메인 페이지 카테고리 추출 실패: {str(e)}")
            return {"main": [], "sub": []}

    async def extract_all_categories_full(self):
        """
        올리브영의 완전한 3단계 카테고리 구조를 추출한다.
        """
        self.logger.info("올리브영 완전한 카테고리 구조 추출 시작")
        
        # 임시 스토리지 생성
        temp_storage = JSONStorage("temp_full_categories.json")
        
        # 크롤러 초기화
        crawler = OliveyoungCrawler(temp_storage, max_workers=1)
        
        try:
            # 크롤러 시작
            await crawler.__aenter__()
            
            # 1단계: 메인 페이지에서 대분류, 중분류 추출
            self.logger.info("1단계: 메인 페이지에서 대분류, 중분류 추출 중...")
            categories = await self.extract_categories_from_main_page(crawler)
            
            if not categories["main"] and not categories["sub"]:
                self.logger.error("메인 페이지 카테고리 추출 실패")
                return
            
            self.logger.info(f"메인 페이지에서 대분류 {len(categories['main'])}개, 중분류 {len(categories['sub'])}개 추출")
            
            # 2단계: 계층 구조 빌드
            hierarchy = self.build_category_hierarchy_new(categories)
            
            # 3단계: 각 중분류에서 소분류 추출
            self.logger.info("2단계: 각 중분류에서 소분류 추출 중...")
            
            total_sub_categories = sum(len(main_data['sub_categories']) for main_data in hierarchy.values())
            processed_sub = 0
            
            for main_id, main_data in hierarchy.items():
                main_name = main_data['name']
                
                for sub_id, sub_data in main_data['sub_categories'].items():
                    processed_sub += 1
                    sub_name = sub_data['name']
                    
                    self.logger.info(f"중분류 처리 ({processed_sub}/{total_sub_categories}): {main_name} > {sub_name}")
                    
                    # 중분류 페이지에서 소분류 추출
                    detail_categories = await self.extract_sub_category_details(crawler, sub_id)
                    
                    # 추출된 소분류를 계층 구조에 추가
                    for detail_cat in detail_categories:
                        detail_id = detail_cat['id']
                        detail_name = detail_cat['name']
                        
                        hierarchy[main_id]['sub_categories'][sub_id]['detail_categories'][detail_id] = {
                            'name': detail_name,
                            'id': detail_id,
                            'type': 'detail'
                        }
                    
                    # 중분류 간 지연
                    await asyncio.sleep(1)
            
            # 4단계: CSV 파일 생성
            await self.save_to_csv(hierarchy)
            
        except Exception as e:
            self.logger.error(f"완전한 카테고리 구조 추출 실패: {str(e)}")
            
        finally:
            # 크롤러 종료
            await crawler.__aexit__(None, None, None)
            
            # 임시 파일 정리
            if os.path.exists("temp_full_categories.json"):
                os.remove("temp_full_categories.json")
    
    async def save_to_csv(self, hierarchy: Dict[str, Dict[str, Any]]):
        """
        계층 구조를 CSV 파일로 저장한다.
        
        Args:
            hierarchy: 완전한 카테고리 계층 구조
        """
        self.logger.info("CSV 파일 생성 중...")
        
        unique_combinations = set()
        total_rows = 0
        
        with open(self.csv_file, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=self.csv_columns)
            writer.writeheader()
            
            for main_id, main_data in hierarchy.items():
                main_name = main_data['name']
                
                # 중분류가 없는 대분류는 단독으로 저장
                if not main_data['sub_categories']:
                    combination = f"{main_name}|{main_id}||"
                    if combination not in unique_combinations:
                        unique_combinations.add(combination)
                        csv_row = {
                            'category_main': main_name,
                            'category_main_id': main_id,
                            'category_sub': '',
                            'category_sub_id': '',
                            'category_detail': '',
                            'category_detail_id': ''
                        }
                        writer.writerow(csv_row)
                        total_rows += 1
                
                for sub_id, sub_data in main_data['sub_categories'].items():
                    sub_name = sub_data['name']
                    
                    # 소분류가 없는 중분류는 중분류까지만 저장
                    if not sub_data['detail_categories']:
                        combination = f"{main_name}|{main_id}|{sub_name}|{sub_id}|"
                        if combination not in unique_combinations:
                            unique_combinations.add(combination)
                            csv_row = {
                                'category_main': main_name,
                                'category_main_id': main_id,
                                'category_sub': sub_name,
                                'category_sub_id': sub_id,
                                'category_detail': '',
                                'category_detail_id': ''
                            }
                            writer.writerow(csv_row)
                            total_rows += 1
                    
                    # 소분류가 있는 경우 3단계 모두 저장
                    for detail_id, detail_data in sub_data['detail_categories'].items():
                        detail_name = detail_data['name']
                        
                        combination = f"{main_name}|{main_id}|{sub_name}|{sub_id}|{detail_name}|{detail_id}"
                        if combination not in unique_combinations:
                            unique_combinations.add(combination)
                            csv_row = {
                                'category_main': main_name,
                                'category_main_id': main_id,
                                'category_sub': sub_name,
                                'category_sub_id': sub_id,
                                'category_detail': detail_name,
                                'category_detail_id': detail_id
                            }
                            writer.writerow(csv_row)
                            total_rows += 1
        
        self.logger.info(f"CSV 파일 생성 완료: {total_rows}개 고유 카테고리 조합을 {self.csv_file}에 저장")
        
        # 결과 요약 출력
        self.print_extraction_summary()
    
    def print_extraction_summary(self):
        """
        추출 결과 요약을 출력한다.
        """
        if not os.path.exists(self.csv_file):
            self.logger.warning("결과 파일이 존재하지 않습니다.")
            return
        
        print("\n" + "="*80)
        print("올리브영 완전한 카테고리 구조 추출 결과")
        print("="*80)
        
        # 통계 수집
        main_categories = set()
        sub_categories = set()
        detail_categories = set()
        total_rows = 0
        
        three_level_count = 0  # 3단계 완전한 카테고리
        two_level_count = 0    # 2단계 카테고리
        one_level_count = 0    # 1단계 카테고리
        
        with open(self.csv_file, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for row in reader:
                total_rows += 1
                
                main = row['category_main'].strip()
                sub = row['category_sub'].strip()
                detail = row['category_detail'].strip()
                
                if main:
                    main_categories.add(main)
                if sub:
                    sub_categories.add(sub)
                if detail:
                    detail_categories.add(detail)
                
                # 레벨 카운팅
                if main and sub and detail:
                    three_level_count += 1
                elif main and sub and not detail:
                    two_level_count += 1
                elif main and not sub and not detail:
                    one_level_count += 1
        
        print(f"총 카테고리 조합: {total_rows}개")
        print(f"고유 대분류: {len(main_categories)}개")
        print(f"고유 중분류: {len(sub_categories)}개")
        print(f"고유 소분류: {len(detail_categories)}개")
        print()
        print(f"3단계 완전 카테고리: {three_level_count}개")
        print(f"2단계 카테고리: {two_level_count}개")
        print(f"1단계 카테고리: {one_level_count}개")
        print()
        
        # 대분류 목록
        print("대분류 목록:")
        for i, main in enumerate(sorted(main_categories), 1):
            print(f"  {i:2d}. {main}")
        print()
        
        # 샘플 카테고리 구조
        print("카테고리 구조 샘플:")
        with open(self.csv_file, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            shown_count = 0
            for row in reader:
                if shown_count >= 30:  # 처음 30개만 표시
                    break
                
                main = row['category_main']
                sub = row['category_sub']
                detail = row['category_detail']
                
                category_path = main
                if sub:
                    category_path += f" > {sub}"
                if detail:
                    category_path += f" > {detail}"
                
                print(f"  {shown_count + 1:2d}. {category_path}")
                shown_count += 1
        
        if total_rows > 30:
            print(f"  ... (총 {total_rows}개 중 30개만 표시)")
        
        print("\n" + "="*80)
        print(f"결과 파일: {self.csv_file}")
        print("="*80)


async def main():
    """메인 실행 함수."""
    extractor = OliveyoungFullCategoryExtractor()
    
    print("올리브영 완전한 3단계 카테고리 구조 추출을 시작합니다...")
    print("이 작업은 다음 단계로 진행됩니다:")
    print("1. 메인 페이지에서 대분류, 중분류 추출")
    print("2. 각 중분류 페이지에서 소분류 추출")
    print("3. 완전한 계층 구조를 CSV로 저장")
    print()
    print("⚠️  주의: 이 작업은 시간이 오래 걸릴 수 있습니다.")
    print()
    
    confirm = input("계속하시겠습니까? (y/N): ").strip().lower()
    if confirm != 'y':
        print("작업이 취소되었습니다.")
        return
    
    await extractor.extract_all_categories_full()


if __name__ == "__main__":
    asyncio.run(main())
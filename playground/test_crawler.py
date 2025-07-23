#!/usr/bin/env python3
"""
크롤러 기본 기능 테스트 플레이그라운드.

사용법:
    python playground/test_crawler.py --branduid=1234567
    python playground/test_crawler.py --help
"""

import sys
import argparse
import asyncio
from pathlib import Path
from urllib.parse import urlparse

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawler.asmama import AsmamaCrawler
from crawler.storage import JSONStorage
from crawler.utils import setup_logger

logger = setup_logger(__name__)

async def test_crawl_from_list(list_url: str, output_dir: str = "playground/results"):
    """
    리스트 페이지 크롤링 테스트.
    """
    print(f"🔍 리스트 페이지 크롤링 테스트 시작: {list_url}")
    
    # 결과 디렉토리 생성
    results_dir = Path(output_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    # 크롤러 초기화
    crawler = AsmamaCrawler(max_workers=1)
    
    try:
        async with crawler:
            print("📡 브라우저 초기화 완료")
            
            # branduid 목록 크롤링
            branduid_list = await crawler.crawl_branduid_list(list_url)

            # branduid 목록에서 제품 크롤링
            product_data = await crawler.crawl_from_branduid_list(branduid_list)
            
            print(f"🔍 총 {len(product_data)}개 제품 크롤링 완료")

            # 저장소 설정
            url_name = "_".join(urlparse(list_url).path.split("/")) + "_" + urlparse(list_url).query
            storage_path = results_dir / f"test_list{url_name}.json"
            storage = JSONStorage(str(storage_path))
            storage.save(product_data)

    except Exception as e:
        print(f"💥 크롤러 실행 중 오류 발생: {str(e)}")
        logger.error(f"크롤러 테스트 실패: {str(e)}", exc_info=True)

async def test_crawl_branduid_list(list_url: str, output_dir: str = "playground/results"):
    """
    리스트 페이지 크롤링 테스트.
    """
    print(f"🔍 리스트 페이지 크롤링 테스트 시작: {list_url}")
    
    # 결과 디렉토리 생성
    results_dir = Path(output_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    
    url_name = "_".join(urlparse(list_url).path.split("/")) + "_" + urlparse(list_url).query

    # 저장소 설정
    storage_path = results_dir / f"test_list{url_name}.json"
    storage = JSONStorage(str(storage_path))

    # 크롤러 초기화
    crawler = AsmamaCrawler(storage=storage, max_workers=1)
    
    try:
        async with crawler:
            print("📡 브라우저 초기화 완료")
            
            # 리스트 페이지 크롤링
            branduid_list = await crawler.crawl_branduid_list(list_url)
            
            print(f"🔍 총 {len(branduid_list)}개 branduid 추출 완료")
            
            # 저장
            storage.save(branduid_list)
 
    except Exception as e:
        print(f"💥 크롤러 실행 중 오류 발생: {str(e)}")
        logger.error(f"크롤러 테스트 실패: {str(e)}", exc_info=True)

async def test_single_product(branduid: str, output_dir: str = "playground/results"):
    """
    단일 제품 크롤링 테스트.
    
    Args:
        branduid: 테스트할 제품의 branduid
        output_dir: 결과 저장 디렉토리
    """
    print(f"🔍 제품 크롤링 테스트 시작: branduid={branduid}")
    
    # 결과 디렉토리 생성
    results_dir = Path(output_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # 저장소 설정
    storage_path = results_dir / f"test_product_{branduid}.json"
    storage = JSONStorage(str(storage_path))
    
    # 크롤러 초기화
    crawler = AsmamaCrawler(storage=storage, max_workers=1)
    
    try:
        async with crawler:
            print("📡 브라우저 초기화 완료")
            
            # 제품 크롤링
            result = await crawler.crawl_single_product(branduid)
            
            if result:
                print("✅ 크롤링 성공!")
                print(f"📄 제품명: {result.get('item_name', 'N/A')}")
                print(f"💰 가격: {result.get('price', 'N/A')}")
                print(f"🎨 옵션 수: {len(result.get('option_info', []))}")
                print(f"🖼️  이미지 수: {len(result.get('images', []))}")
                print(f"💾 저장 위치: {storage_path}")

            else:
                print("❌ 크롤링 실패")
                print("🔍 로그 파일을 확인하여 상세 오류를 확인하세요")
                
    except Exception as e:
        print(f"💥 크롤러 실행 중 오류 발생: {str(e)}")
        logger.error(f"크롤러 테스트 실패: {str(e)}", exc_info=True)


def test_crawler_initialization():
    """
    크롤러 초기화 테스트.
    """
    print("🔧 크롤러 초기화 테스트...")
    
    try:
        # 기본 초기화
        crawler = AsmamaCrawler()
        print(f"✅ 기본 초기화 성공 (max_workers: {crawler.max_workers})")
        
        # 커스텀 설정
        storage = JSONStorage("playground/results/test_init.json")
        crawler_custom = AsmamaCrawler(storage=storage, max_workers=1)
        print(f"✅ 커스텀 초기화 성공 (max_workers: {crawler_custom.max_workers})")
        
        return True
        
    except Exception as e:
        print(f"❌ 초기화 실패: {str(e)}")
        return False


def analyze_results(results_dir: str = "playground/results"):
    """
    저장된 결과 분석.
    
    Args:
        results_dir: 결과 디렉토리
    """
    print("📊 결과 분석...")
    
    results_path = Path(results_dir)
    if not results_path.exists():
        print("❌ 결과 디렉토리가 없습니다.")
        return
    
    json_files = list(results_path.glob("*.json"))
    
    if not json_files:
        print("❌ 결과 파일이 없습니다.")
        return
    
    print(f"📁 발견된 결과 파일: {len(json_files)}개")
    
    total_products = 0
    for json_file in json_files:
        try:
            storage = JSONStorage(str(json_file))
            data = storage.load()
            total_products += len(data)
            print(f"   📄 {json_file.name}: {len(data)}개 제품")
        except Exception as e:
            print(f"   ❌ {json_file.name}: 읽기 오류 - {str(e)}")
    
    print(f"📈 총 크롤링된 제품: {total_products}개")


def main():
    # """메인 함수."""
    # parser = argparse.ArgumentParser(description="크롤러 기본 기능 테스트")
    # parser.add_argument(
    #     "--branduid",
    #     type=str,
    #     help="테스트할 제품의 branduid"
    # )
    # parser.add_argument(
    #     "--init-test",
    #     action="store_true",
    #     help="크롤러 초기화 테스트만 실행"
    # )
    # parser.add_argument(
    #     "--analyze",
    #     action="store_true",
    #     help="저장된 결과 분석"
    # )
    # parser.add_argument(
    #     "--output-dir",
    #     default="playground/results",
    #     help="결과 저장 디렉토리"
    # )
    
    # args = parser.parse_args()
    
    # print("🚀 크롤러 테스트 플레이그라운드")
    # print("=" * 40)
    
    # if args.init_test:
    #     success = test_crawler_initialization()
    #     sys.exit(0 if success else 1)
    
    # if args.analyze:
    #     analyze_results(args.output_dir)
    #     return
    
    # if not args.branduid:
    #     print("❌ --branduid 인자가 필요합니다.")
    #     print("💡 예시: python playground/test_crawler.py --branduid=1234567")
    #     sys.exit(1)
    
    # # 크롤러 초기화 테스트
    # if not test_crawler_initialization():
    #     sys.exit(1)
    
    # # 제품 크롤링 테스트
    # asyncio.run(test_single_product(args.branduid, args.output_dir))

    """메인 함수."""
    parser = argparse.ArgumentParser(description="크롤러 리스트 추출 기능 테스트")
    parser.add_argument(
        "--list-url",
        type=str,
        help="테스트할 리스트 페이지 URL"
    )
    parser.add_argument(
        "--output-dir",
        default="playground/results",
        help="결과 저장 디렉토리"
    )
    args = parser.parse_args()

    print("🚀 크롤러 테스트 플레이그라운드")
    print("=" * 40)

    if not args.list_url:
        print("❌ --list-url 인자가 필요합니다.")
        print("💡 예시: python playground/test_crawler.py --list-url=http://www.asmama.com/shop/bestseller.html?xcode=REVIEW")
        sys.exit(1)
    
    # 크롤러 초기화 테스트
    if not test_crawler_initialization():
        sys.exit(1)
    
    # 제품 크롤링 테스트
    asyncio.run(test_crawl_from_list(args.list_url, args.output_dir))


if __name__ == "__main__":
    main()
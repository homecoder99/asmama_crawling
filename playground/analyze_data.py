#!/usr/bin/env python3
"""
크롤링 결과 데이터 분석 플레이그라운드.

Excel 파일이나 JSON 파일에서 크롤링 결과를 로드하여 통계 분석을 수행합니다.

사용법:
    python playground/analyze_data.py --input=data/asmama_products.xlsx
    python playground/analyze_data.py --input=playground/results/*.json --format=json
"""

import sys
import argparse
import json
from pathlib import Path
from typing import List, Dict, Any
import glob

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from crawler.utils import setup_logger, parse_price

logger = setup_logger(__name__)


class DataAnalyzer:
    """크롤링 데이터 분석기."""
    
    def __init__(self):
        """분석기 초기화."""
        self.data: List[Dict[str, Any]] = []
    
    def load_excel(self, file_path: str) -> bool:
        """
        Excel 파일에서 데이터를 로드한다.
        
        Args:
            file_path: Excel 파일 경로
            
        Returns:
            로드 성공 여부
        """
        if not PANDAS_AVAILABLE:
            print("❌ pandas가 설치되지 않았습니다. pip install pandas를 실행하세요.")
            return False
        
        try:
            df = pd.read_excel(file_path)
            
            # JSON 문자열 컬럼을 리스트로 변환
            for col in df.columns:
                if col in ['options', 'image_urls']:
                    df[col] = df[col].apply(
                        lambda x: json.loads(x) if isinstance(x, str) and x.startswith('[') else x
                    )
            
            self.data = df.to_dict('records')
            print(f"✅ Excel 데이터 로드 완료: {len(self.data)}개 항목")
            return True
            
        except Exception as e:
            print(f"❌ Excel 파일 로드 실패: {str(e)}")
            return False
    
    def load_json_files(self, pattern: str) -> bool:
        """
        JSON 파일들에서 데이터를 로드한다.
        
        Args:
            pattern: 파일 패턴 (glob 형식)
            
        Returns:
            로드 성공 여부
        """
        try:
            files = glob.glob(pattern)
            
            if not files:
                print(f"❌ 패턴에 맞는 파일이 없습니다: {pattern}")
                return False
            
            all_data = []
            
            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_data = json.load(f)
                    
                    if isinstance(file_data, list):
                        all_data.extend(file_data)
                    elif isinstance(file_data, dict):
                        all_data.append(file_data)
                    
                    print(f"📄 {Path(file_path).name}: {len(file_data) if isinstance(file_data, list) else 1}개 항목")
                    
                except Exception as e:
                    print(f"⚠️  {Path(file_path).name} 로드 실패: {str(e)}")
            
            self.data = all_data
            print(f"✅ JSON 데이터 로드 완료: {len(self.data)}개 항목")
            return True
            
        except Exception as e:
            print(f"❌ JSON 파일 로드 실패: {str(e)}")
            return False
    
    def basic_statistics(self) -> Dict[str, Any]:
        """
        기본 통계 정보를 생성한다.
        
        Returns:
            통계 정보 딕셔너리
        """
        if not self.data:
            return {"error": "데이터가 없습니다"}
        
        stats = {
            "total_products": len(self.data),
            "columns": set(),
            "branduid_stats": {},
            "name_stats": {},
            "price_stats": {},
            "options_stats": {},
            "images_stats": {}
        }
        
        # 컬럼 수집
        for item in self.data:
            stats["columns"].update(item.keys())
        stats["columns"] = list(stats["columns"])
        
        # branduid 통계
        branduid_list = [item.get('branduid') for item in self.data if item.get('branduid')]
        stats["branduid_stats"] = {
            "count": len(branduid_list),
            "unique_count": len(set(branduid_list)),
            "sample": branduid_list[:5]
        }
        
        # 제품명 통계
        names = [item.get('name') for item in self.data if item.get('name')]
        stats["name_stats"] = {
            "count": len(names),
            "empty_count": len(self.data) - len(names),
            "avg_length": sum(len(name) for name in names) / len(names) if names else 0,
            "sample": names[:3]
        }
        
        # 가격 통계
        prices = []
        for item in self.data:
            price = item.get('price')
            if isinstance(price, (int, float)) and price > 0:
                prices.append(price)
            elif isinstance(price, str):
                parsed_price = parse_price(price)
                if parsed_price:
                    prices.append(parsed_price)
        
        if prices:
            stats["price_stats"] = {
                "count": len(prices),
                "min": min(prices),
                "max": max(prices),
                "avg": sum(prices) / len(prices),
                "empty_count": len(self.data) - len(prices)
            }
        
        # 옵션 통계
        options_data = []
        for item in self.data:
            options = item.get('options', [])
            if isinstance(options, list):
                options_data.extend(options)
        
        stats["options_stats"] = {
            "total_options": len(options_data),
            "unique_options": len(set(options_data)),
            "products_with_options": len([item for item in self.data if item.get('options')]),
            "common_options": self._get_most_common(options_data, 5)
        }
        
        # 이미지 통계
        image_counts = []
        for item in self.data:
            images = item.get('image_urls', [])
            if isinstance(images, list):
                image_counts.append(len(images))
        
        if image_counts:
            stats["images_stats"] = {
                "products_with_images": len([c for c in image_counts if c > 0]),
                "total_images": sum(image_counts),
                "avg_images_per_product": sum(image_counts) / len(image_counts),
                "max_images": max(image_counts),
                "min_images": min(image_counts)
            }
        
        return stats
    
    def _get_most_common(self, items: List[str], limit: int = 5) -> List[tuple]:
        """
        가장 많이 나타나는 항목들을 반환한다.
        
        Args:
            items: 항목 리스트
            limit: 반환할 최대 개수
            
        Returns:
            (항목, 개수) 튜플 리스트
        """
        from collections import Counter
        counter = Counter(items)
        return counter.most_common(limit)
    
    def quality_analysis(self) -> Dict[str, Any]:
        """
        데이터 품질 분석을 수행한다.
        
        Returns:
            품질 분석 결과
        """
        if not self.data:
            return {"error": "데이터가 없습니다"}
        
        quality = {
            "completeness": {},
            "validity": {},
            "consistency": {},
            "issues": []
        }
        
        # 완성도 분석
        required_fields = ['branduid', 'name', 'price']
        for field in required_fields:
            filled_count = len([item for item in self.data if item.get(field)])
            quality["completeness"][field] = {
                "filled": filled_count,
                "empty": len(self.data) - filled_count,
                "percentage": (filled_count / len(self.data)) * 100
            }
        
        # 유효성 분석
        # 가격 유효성
        valid_prices = 0
        for item in self.data:
            price = item.get('price')
            if isinstance(price, (int, float)) and price > 0:
                valid_prices += 1
            elif isinstance(price, str) and parse_price(price):
                valid_prices += 1
        
        quality["validity"]["price"] = {
            "valid": valid_prices,
            "invalid": len(self.data) - valid_prices,
            "percentage": (valid_prices / len(self.data)) * 100
        }
        
        # 일관성 분석
        # branduid 중복 검사
        branduid_list = [item.get('branduid') for item in self.data if item.get('branduid')]
        duplicates = len(branduid_list) - len(set(branduid_list))
        quality["consistency"]["branduid_duplicates"] = duplicates
        
        # 이슈 발견
        if duplicates > 0:
            quality["issues"].append(f"branduid 중복: {duplicates}개")
        
        empty_names = len(self.data) - len([item for item in self.data if item.get('name')])
        if empty_names > 0:
            quality["issues"].append(f"제품명 누락: {empty_names}개")
        
        return quality
    
    def generate_report(self) -> str:
        """
        분석 보고서를 생성한다.
        
        Returns:
            분석 보고서 텍스트
        """
        stats = self.basic_statistics()
        quality = self.quality_analysis()
        
        report = []
        report.append("📊 크롤링 데이터 분석 보고서")
        report.append("=" * 50)
        report.append("")
        
        # 기본 통계
        report.append("📈 기본 통계:")
        report.append(f"  총 제품 수: {stats.get('total_products', 0):,}개")
        report.append(f"  데이터 컬럼: {', '.join(stats.get('columns', []))}")
        report.append("")
        
        # branduid 통계
        if 'branduid_stats' in stats:
            bs = stats['branduid_stats']
            report.append("🆔 Branduid 통계:")
            report.append(f"  총 개수: {bs.get('count', 0)}개")
            report.append(f"  고유 개수: {bs.get('unique_count', 0)}개")
            report.append("")
        
        # 제품명 통계
        if 'name_stats' in stats:
            ns = stats['name_stats']
            report.append("📝 제품명 통계:")
            report.append(f"  제품명 있음: {ns.get('count', 0)}개")
            report.append(f"  제품명 없음: {ns.get('empty_count', 0)}개")
            report.append(f"  평균 길이: {ns.get('avg_length', 0):.1f}자")
            report.append("")
        
        # 가격 통계
        if 'price_stats' in stats:
            ps = stats['price_stats']
            report.append("💰 가격 통계:")
            report.append(f"  가격 있음: {ps.get('count', 0)}개")
            report.append(f"  최저가: {ps.get('min', 0):,}원")
            report.append(f"  최고가: {ps.get('max', 0):,}원")
            report.append(f"  평균가: {ps.get('avg', 0):,.0f}원")
            report.append("")
        
        # 옵션 통계
        if 'options_stats' in stats:
            os = stats['options_stats']
            report.append("🎨 옵션 통계:")
            report.append(f"  총 옵션 수: {os.get('total_options', 0)}개")
            report.append(f"  고유 옵션 수: {os.get('unique_options', 0)}개")
            report.append(f"  옵션 있는 제품: {os.get('products_with_options', 0)}개")
            if os.get('common_options'):
                report.append("  인기 옵션:")
                for option, count in os['common_options']:
                    report.append(f"    - {option}: {count}개")
            report.append("")
        
        # 이미지 통계
        if 'images_stats' in stats:
            imgs = stats['images_stats']
            report.append("🖼️  이미지 통계:")
            report.append(f"  이미지 있는 제품: {imgs.get('products_with_images', 0)}개")
            report.append(f"  총 이미지 수: {imgs.get('total_images', 0)}개")
            report.append(f"  제품당 평균 이미지: {imgs.get('avg_images_per_product', 0):.1f}개")
            report.append("")
        
        # 품질 분석
        report.append("🔍 데이터 품질 분석:")
        if 'completeness' in quality:
            for field, comp in quality['completeness'].items():
                report.append(f"  {field} 완성도: {comp.get('percentage', 0):.1f}% ({comp.get('filled', 0)}/{comp.get('filled', 0) + comp.get('empty', 0)})")
        
        if quality.get('issues'):
            report.append("")
            report.append("⚠️  발견된 이슈:")
            for issue in quality['issues']:
                report.append(f"  - {issue}")
        
        return "\n".join(report)


def save_report(report: str, output_file: str = "playground/results/analysis_report.txt"):
    """
    분석 보고서를 파일로 저장한다.
    
    Args:
        report: 보고서 텍스트
        output_file: 저장할 파일 경로
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"💾 보고서 저장 완료: {output_path}")


def main():
    """메인 함수."""
    parser = argparse.ArgumentParser(description="크롤링 데이터 분석 도구")
    parser.add_argument(
        "--input",
        required=True,
        help="분석할 데이터 파일 (Excel 또는 JSON 패턴)"
    )
    parser.add_argument(
        "--format",
        choices=["excel", "json"],
        help="입력 파일 형식 (자동 감지됨)"
    )
    parser.add_argument(
        "--output",
        default="playground/results/analysis_report.txt",
        help="보고서 저장 파일"
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="상세 분석 모드"
    )
    
    args = parser.parse_args()
    
    print("📊 데이터 분석 플레이그라운드")
    print("=" * 40)
    
    analyzer = DataAnalyzer()
    
    # 파일 형식 자동 감지
    input_path = args.input
    if args.format == "json" or "*" in input_path or input_path.endswith(".json"):
        success = analyzer.load_json_files(input_path)
    elif args.format == "excel" or input_path.endswith((".xlsx", ".xls")):
        success = analyzer.load_excel(input_path)
    else:
        print("❌ 파일 형식을 감지할 수 없습니다. --format 옵션을 사용하세요.")
        sys.exit(1)
    
    if not success:
        sys.exit(1)
    
    # 분석 수행
    print("\n🔍 분석 수행 중...")
    report = analyzer.generate_report()
    
    # 결과 출력
    print("\n" + report)
    
    # 파일 저장
    save_report(report, args.output)
    
    if args.detailed:
        print("\n📋 상세 통계 (JSON):")
        stats = analyzer.basic_statistics()
        print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
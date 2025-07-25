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
from typing import List, Dict, Any, Optional, Tuple
import glob

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from crawler.utils import setup_logger, parse_price
from crawler.validator import ProductValidator

logger = setup_logger(__name__)


def safe_str_check(value) -> bool:
    """
    값이 유효한 문자열인지 안전하게 확인한다.
    
    Args:
        value: 확인할 값
        
    Returns:
        유효한 문자열 여부
    """
    if value is None:
        return False
    if isinstance(value, float):
        import math
        if math.isnan(value):
            return False
        return str(value).strip() != ""
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (int, list)):
        return True
    return False


class DataAnalyzer:
    """크롤링 데이터 분석기."""
    
    def __init__(self):
        """분석기 초기화."""
        self.data: List[Dict[str, Any]] = []
        self.validation_log_path: Optional[str] = None
        self.validator: Optional[ProductValidator] = None
    
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
            "item_name_stats": {},
            "price_stats": {},
            "category_stats": {},
            "option_stats": {},
            "images_stats": {},
            "celeb_stats": {},
            "origin_country_stats": {}
        }
        
        # 컬럼 수집
        for item in self.data:
            stats["columns"].update(item.keys())
        stats["columns"] = list(stats["columns"])
        
        # branduid 통계 (중복 검사 포함)
        branduid_list = [item.get('branduid') for item in self.data if item.get('branduid')]
        unique_branduids = set(branduid_list)
        duplicates_count = len(branduid_list) - len(unique_branduids)
        
        # 중복된 branduid 찾기
        from collections import Counter
        branduid_counts = Counter(branduid_list)
        duplicate_branduids = {uid: count for uid, count in branduid_counts.items() if count > 1}
        
        stats["branduid_stats"] = {
            "count": len(branduid_list),
            "unique_count": len(unique_branduids),
            "duplicates_count": duplicates_count,
            "duplicate_branduids": duplicate_branduids,
            "sample": branduid_list[:5]
        }
        
        # 제품명 통계 (현재 스키마: item_name)
        item_names = [item.get('item_name') for item in self.data if item.get('item_name')]
        stats["item_name_stats"] = {
            "count": len(item_names),
            "empty_count": len(self.data) - len(item_names),
            "avg_length": sum(len(name) for name in item_names) / len(item_names) if item_names else 0,
            "sample": item_names[:3]
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
        
        # 카테고리 통계
        categories = [item.get('category_name') for item in self.data if item.get('category_name')]
        stats["category_stats"] = {
            "count": len(categories),
            "empty_count": len(self.data) - len(categories),
            "unique_categories": len(set(categories)),
            "distribution": self._get_most_common(categories, 10)
        }
        
        # 옵션 통계 (안전한 문자열 처리)
        products_with_options = [item for item in self.data if item.get('is_option_available')]
        option_info_present = [item for item in self.data if safe_str_check(item.get('option_info'))]
        
        stats["option_stats"] = {
            "products_marked_with_options": len(products_with_options),
            "products_with_option_info": len(option_info_present),
            "option_consistency_rate": (len(option_info_present) / len(products_with_options) * 100) if products_with_options else 0
        }
        
        # 셀럽 정보 통계 (안전한 문자열 처리)
        celeb_info = []
        for item in self.data:
            celeb_value = item.get('related_celeb')
            if safe_str_check(celeb_value):
                if isinstance(celeb_value, str):
                    celeb_info.append(celeb_value.strip())
                else:
                    celeb_info.append(str(celeb_value).strip())
        
        stats["celeb_stats"] = {
            "count": len(celeb_info),
            "empty_count": len(self.data) - len(celeb_info),
            "percentage": (len(celeb_info) / len(self.data) * 100) if self.data else 0,
            "sample": celeb_info[:3]
        }
        
        # 원산지 통계 (안전한 문자열 처리)
        origin_countries = []
        for item in self.data:
            origin_value = item.get('origin_country')
            if safe_str_check(origin_value):
                if isinstance(origin_value, str):
                    origin_countries.append(origin_value.strip())
                else:
                    origin_countries.append(str(origin_value).strip())
        
        stats["origin_country_stats"] = {
            "count": len(origin_countries),
            "empty_count": len(self.data) - len(origin_countries),
            "unique_countries": len(set(origin_countries)),
            "distribution": self._get_most_common(origin_countries, 10)
        }
        
        # 이미지 통계 (현재 스키마: images는 $$로 구분된 문자열)
        images_present = []
        for item in self.data:
            images = item.get('images', '')
            if images and images.strip():
                # $$로 구분된 이미지 URL 개수 계산
                image_count = len([img for img in images.split('$$') if img.strip()])
                images_present.append(image_count)
            else:
                images_present.append(0)
        
        if images_present:
            stats["images_stats"] = {
                "products_with_images": len([c for c in images_present if c > 0]),
                "total_images": sum(images_present),
                "avg_images_per_product": sum(images_present) / len(images_present),
                "max_images": max(images_present),
                "min_images": min(images_present)
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
        
        # 완성도 분석 (현재 스키마의 필수 필드들) - 안전한 문자열 처리
        required_fields = ['branduid', 'item_name', 'price', 'category_name', 'images', 'origin_country']
        for field in required_fields:
            filled_count = len([item for item in self.data if safe_str_check(item.get(field))])
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
        
        empty_names = len(self.data) - len([item for item in self.data if item.get('item_name')])
        if empty_names > 0:
            quality["issues"].append(f"제품명 누락: {empty_names}개")
        
        # 옵션 일치성 검사 (안전한 문자열 처리)
        option_available_count = len([item for item in self.data if item.get('is_option_available')])
        option_info_count = len([item for item in self.data if safe_str_check(item.get('option_info'))])
        
        if option_available_count != option_info_count:
            quality["issues"].append(f"옵션 정보 불일치: 옵션 가능 {option_available_count}개 vs 옵션 정보 {option_info_count}개")
        
        return quality
    
    def validation_analysis(self, validation_log_path: str = None) -> Dict[str, Any]:
        """
        검증 로그 분석을 수행한다.
        
        Args:
            validation_log_path: 검증 로그 파일 경로
            
        Returns:
            검증 분석 결과
        """
        if not validation_log_path:
            # 인스턴스 변수 또는 기본 경로 사용
            validation_log_path = self.validation_log_path or "logs/final_validation_stats.json"
        
        try:
            with open(validation_log_path, 'r', encoding='utf-8') as f:
                validation_data = json.load(f)
            
            analysis = {
                "validation_summary": validation_data.get("summary", {}),
                "removal_breakdown": validation_data.get("removal_breakdown", {}),
                "validation_config": validation_data.get("validation_config", {}),
                "detailed_reasons": validation_data.get("detailed_reasons", [])
            }
            
            # 제거 이유별 통계 분석
            if analysis["detailed_reasons"]:
                reason_counts = {}
                for reason_item in analysis["detailed_reasons"]:
                    reason = reason_item.get("reason", "unknown")
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1
                
                analysis["reason_distribution"] = reason_counts
            
            return analysis
            
        except FileNotFoundError:
            print(f"⚠️  검증 로그 파일을 찾을 수 없습니다: {validation_log_path}")
            return {}
        except Exception as e:
            print(f"❌ 검증 로그 분석 실패: {str(e)}")
            return {}
    
    def remove_duplicates(self, save_deduplicated: bool = True, output_path: str = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        branduid 중복을 제거하고 정리된 데이터를 반환한다.
        
        Args:
            save_deduplicated: 중복 제거된 데이터를 파일로 저장할지 여부
            output_path: 중복 제거된 데이터 저장 경로 (기본: data/deduplicated_products.xlsx)
            
        Returns:
            (중복_제거된_데이터, 중복_제거_통계)
        """
        if not self.data:
            print("❌ 중복 제거할 데이터가 없습니다. 먼저 데이터를 로드하세요.")
            return [], {}
        
        print(f"🔍 branduid 중복 제거 시작: {len(self.data)}개 제품")
        
        # branduid별로 첫 번째 항목만 유지 (순서 보장)
        seen_branduids = set()
        deduplicated_data = []
        removed_items = []
        
        for item in self.data:
            branduid = item.get('branduid')
            if branduid and branduid not in seen_branduids:
                seen_branduids.add(branduid)
                deduplicated_data.append(item)
            elif branduid:
                removed_items.append(item)
                print(f"  중복 제거: {branduid}")
        
        # 통계 생성
        dedup_stats = {
            "original_count": len(self.data),
            "deduplicated_count": len(deduplicated_data),
            "removed_count": len(removed_items),
            "unique_branduids": len(seen_branduids)
        }
        
        print(f"✅ 중복 제거 완료: {dedup_stats['original_count']} → {dedup_stats['deduplicated_count']}개 ({dedup_stats['removed_count']}개 제거)")
        
        # 중복 제거된 데이터 저장
        if save_deduplicated and deduplicated_data:
            if not output_path:
                output_path = "data/deduplicated_products.xlsx"
            
            try:
                from crawler.storage import ExcelStorage
                storage = ExcelStorage(output_path)
                storage.clear()  # 기존 데이터 삭제
                storage.save(deduplicated_data)
                print(f"💾 중복 제거된 데이터 저장: {output_path} ({len(deduplicated_data)}개 제품)")
            except Exception as e:
                print(f"❌ 중복 제거된 데이터 저장 실패: {str(e)}")
        
        return deduplicated_data, dedup_stats
    
    def validate_data(self, require_celeb_info: bool = True, save_validated: bool = True, output_path: str = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        로드된 데이터에 대해 검증을 수행한다.
        
        Args:
            require_celeb_info: 셀럽 정보 필수 여부
            save_validated: 검증된 데이터를 파일로 저장할지 여부
            output_path: 검증된 데이터 저장 경로 (기본: data/validated_products.xlsx)
            
        Returns:
            (검증된_데이터, 검증_통계)
        """
        if not self.data:
            print("❌ 검증할 데이터가 없습니다. 먼저 데이터를 로드하세요.")
            return [], {}
        
        print(f"🔍 데이터 검증 시작: {len(self.data)}개 제품 (셀럽 정보 필수: {require_celeb_info})")
        
        # 1단계: 자동으로 중복 제거 수행
        print("1️⃣ branduid 중복 제거 중...")
        deduplicated_data, dedup_stats = self.remove_duplicates(save_deduplicated=False)
        
        if dedup_stats['removed_count'] > 0:
            print(f"   ✅ 중복 제거 완료: {dedup_stats['removed_count']}개 제거")
            self.data = deduplicated_data  # 중복 제거된 데이터로 교체
        else:
            print("   ✅ 중복 없음")
        
        # 2단계: 검증기 초기화 및 검증 수행
        print("2️⃣ 데이터 품질 검증 중...")
        self.validator = ProductValidator(require_celeb_info=require_celeb_info)
        
        # 검증 수행
        validated_products, validation_stats = self.validator.validate_products(self.data)
        
        # 검증 보고서 생성
        validation_report = self.validator.generate_validation_report()
        print("\n" + validation_report)
        
        # 검증 로그 저장
        from pathlib import Path
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        # 상세 로그 저장
        log_file = logs_dir / "validation_stats.json"
        self.validator.save_validation_log(str(log_file))
        print(f"📄 검증 로그 저장: {log_file}")
        
        # 보고서 저장
        report_file = logs_dir / "validation_report.txt"
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(validation_report)
            print(f"📄 검증 보고서 저장: {report_file}")
        except Exception as e:
            print(f"⚠️ 검증 보고서 저장 실패: {str(e)}")
        
        # 검증된 데이터 저장
        if save_validated and validated_products:
            if not output_path:
                output_path = "data/validated_products.xlsx"
            
            try:
                from crawler.storage import ExcelStorage
                storage = ExcelStorage(output_path)
                storage.clear()  # 기존 데이터 삭제
                storage.save(validated_products)
                print(f"✅ 검증된 데이터 저장: {output_path} ({len(validated_products)}개 제품)")
            except Exception as e:
                print(f"❌ 검증된 데이터 저장 실패: {str(e)}")
        
        return validated_products, validation_stats.to_dict()
    
    def generate_report(self, include_validation: bool = True) -> str:
        """
        분석 보고서를 생성한다.
        
        Args:
            include_validation: 검증 분석 포함 여부
        
        Returns:
            분석 보고서 텍스트
        """
        stats = self.basic_statistics()
        quality = self.quality_analysis()
        validation = self.validation_analysis() if include_validation else {}
        
        report = []
        report.append("📊 크롤링 데이터 분석 보고서")
        report.append("=" * 50)
        report.append("")
        
        # 기본 통계
        report.append("📈 기본 통계:")
        report.append(f"  총 제품 수: {stats.get('total_products', 0):,}개")
        report.append(f"  데이터 컬럼: {', '.join(stats.get('columns', []))}")
        report.append("")
        
        # branduid 통계 (중복 정보 포함)
        if 'branduid_stats' in stats:
            bs = stats['branduid_stats']
            report.append("🆔 Branduid 통계:")
            report.append(f"  총 개수: {bs.get('count', 0)}개")
            report.append(f"  고유 개수: {bs.get('unique_count', 0)}개")
            
            duplicates_count = bs.get('duplicates_count', 0)
            if duplicates_count > 0:
                report.append(f"  ⚠️ 중복 개수: {duplicates_count}개")
                duplicate_branduids = bs.get('duplicate_branduids', {})
                if duplicate_branduids:
                    report.append("  중복된 branduid (상위 5개):")
                    for uid, count in list(duplicate_branduids.items())[:5]:
                        report.append(f"    - {uid}: {count}회 중복")
            else:
                report.append("  ✅ 중복 없음")
            report.append("")
        
        # 제품명 통계
        if 'item_name_stats' in stats:
            ns = stats['item_name_stats']
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
        
        # 카테고리 통계
        if 'category_stats' in stats:
            cs = stats['category_stats']
            report.append("📂 카테고리 통계:")
            report.append(f"  카테고리 있음: {cs.get('count', 0)}개")
            report.append(f"  카테고리 없음: {cs.get('empty_count', 0)}개")
            report.append(f"  고유 카테고리: {cs.get('unique_categories', 0)}개")
            if cs.get('distribution'):
                report.append("  카테고리 분포:")
                for category, count in cs['distribution']:
                    report.append(f"    - {category}: {count}개")
            report.append("")

        # 옵션 통계
        if 'option_stats' in stats:
            os = stats['option_stats']
            report.append("🎨 옵션 통계:")
            report.append(f"  옵션 가능으로 표시된 제품: {os.get('products_marked_with_options', 0)}개")
            report.append(f"  옵션 정보가 있는 제품: {os.get('products_with_option_info', 0)}개")
            report.append(f"  옵션 일치율: {os.get('option_consistency_rate', 0):.1f}%")
            report.append("")
        
        # 이미지 통계
        if 'images_stats' in stats:
            imgs = stats['images_stats']
            report.append("🖼️  이미지 통계:")
            report.append(f"  이미지 있는 제품: {imgs.get('products_with_images', 0)}개")
            report.append(f"  총 이미지 수: {imgs.get('total_images', 0)}개")
            report.append(f"  제품당 평균 이미지: {imgs.get('avg_images_per_product', 0):.1f}개")
            report.append("")
        
        # 셀럽 정보 통계
        if 'celeb_stats' in stats:
            celeb = stats['celeb_stats']
            report.append("⭐ 셀럽 정보 통계:")
            report.append(f"  셀럽 정보 있음: {celeb.get('count', 0)}개")
            report.append(f"  셀럽 정보 없음: {celeb.get('empty_count', 0)}개")
            report.append(f"  셀럽 정보 비율: {celeb.get('percentage', 0):.1f}%")
            report.append("")
        
        # 원산지 통계
        if 'origin_country_stats' in stats:
            origin = stats['origin_country_stats']
            report.append("🌍 원산지 통계:")
            report.append(f"  원산지 정보 있음: {origin.get('count', 0)}개")
            report.append(f"  원산지 정보 없음: {origin.get('empty_count', 0)}개")
            report.append(f"  고유 원산지: {origin.get('unique_countries', 0)}개")
            if origin.get('distribution'):
                report.append("  원산지 분포:")
                for country, count in origin['distribution']:
                    report.append(f"    - {country}: {count}개")
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
        
        # 검증 분석 결과 추가
        if validation and include_validation:
            report.append("")
            report.append("🔍 데이터 검증 결과:")
            
            validation_summary = validation.get("validation_summary", {})
            if validation_summary:
                report.append(f"  검증 처리된 제품 수: {validation_summary.get('total_products', 0):,}개")
                report.append(f"  검증 통과 제품 수: {validation_summary.get('valid_products', 0):,}개")
                report.append(f"  제거된 제품 수: {validation_summary.get('removed_products', 0):,}개")
                report.append(f"  검증 성공률: {validation_summary.get('success_rate', 0):.1f}%")
            
            removal_breakdown = validation.get("removal_breakdown", {})
            if removal_breakdown:
                report.append("")
                report.append("📋 제거 이유별 통계:")
                for reason, count in removal_breakdown.items():
                    if count > 0:
                        reason_names = {
                            "missing_required_fields": "필수 필드 누락",
                            "invalid_price": "유효하지 않은 가격",
                            "missing_images": "이미지 누락",
                            "missing_origin_country": "원산지 정보 누락",
                            "option_inconsistency": "옵션 정보 불일치",
                            "discontinued_products": "판매종료 상품",
                            "missing_celeb_info": "셀럽 정보 누락"
                        }
                        reason_name = reason_names.get(reason, reason)
                        report.append(f"  {reason_name}: {count}개")
            
            validation_config = validation.get("validation_config", {})
            if validation_config:
                report.append("")
                report.append("⚙️ 검증 설정:")
                required_fields = validation_config.get("required_fields", [])
                if required_fields:
                    report.append(f"  필수 필드: {', '.join(required_fields)}")
                require_celeb = validation_config.get("require_celeb_info", True)
                report.append(f"  셀럽 정보 필수: {'예' if require_celeb else '아니오'}")
        
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
    parser.add_argument(
        "--validation-log",
        help="검증 로그 파일 경로 (기본: logs/final_validation_stats.json)"
    )
    parser.add_argument(
        "--no-validation",
        action="store_true",
        help="검증 분석 제외"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="데이터 검증 수행"
    )
    parser.add_argument(
        "--require-celeb-info",
        action="store_true",
        help="셀럽 정보를 필수로 설정"
    )
    parser.add_argument(
        "--validated-output",
        help="검증된 데이터 저장 경로 (기본: data/validated_products.xlsx)"
    )
    parser.add_argument(
        "--remove-duplicates",
        action="store_true",
        help="branduid 중복 제거 수행"
    )
    parser.add_argument(
        "--deduplicated-output",
        help="중복 제거된 데이터 저장 경로 (기본: data/deduplicated_products.xlsx)"
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
    
    # 검증 로그 경로 설정
    if args.validation_log:
        analyzer.validation_log_path = args.validation_log
    
    # 중복 제거 수행 (요청된 경우)
    if args.remove_duplicates:
        print("\n🔄 branduid 중복 제거 수행 중...")
        deduplicated_data, dedup_stats = analyzer.remove_duplicates(
            save_deduplicated=True,
            output_path=args.deduplicated_output
        )
        
        # 중복 제거된 데이터로 교체
        analyzer.data = deduplicated_data
        print(f"📊 분석 대상 데이터 업데이트: {dedup_stats['deduplicated_count']}개 제품")
    
    # 데이터 검증 수행 (요청된 경우) - 자동으로 중복 제거 포함
    if args.validate:
        print("\n🔍 데이터 검증 수행 중...")
        _, validation_stats = analyzer.validate_data(
            require_celeb_info=args.require_celeb_info,
            save_validated=True,
            output_path=args.validated_output
        )
        
        # 검증 후 validated 데이터 경로 설정 (보고서에서 검증 결과를 표시하기 위해)
        analyzer.validation_log_path = "logs/validation_stats.json"
    
    # 분석 수행
    print("\n🔍 분석 수행 중...")
    include_validation = not args.no_validation
    report = analyzer.generate_report(include_validation=include_validation)
    
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
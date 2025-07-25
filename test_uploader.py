#!/usr/bin/env python3
"""
업로더 빠른 테스트 스크립트

사용법:
    python test_uploader.py
"""

import sys
import subprocess
from pathlib import Path


def run_command(cmd, description):
    """명령어 실행 및 결과 출력"""
    print(f"\n🔄 {description}")
    print(f"실행: {cmd}")
    print("-" * 60)
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.stdout:
            print("출력:")
            print(result.stdout)
        
        if result.stderr:
            print("오류:")
            print(result.stderr)
        
        if result.returncode == 0:
            print(f"✅ {description} 성공")
        else:
            print(f"❌ {description} 실패 (코드: {result.returncode})")
            
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ 명령어 실행 실패: {e}")
        return False


def check_files():
    """필요한 파일들 확인"""
    print("\n📁 파일 확인")
    print("-" * 60)
    
    files_to_check = [
        "data/validated_products_celeb.xlsx",
        "templates/upload/sample.xlsx",
        "templates/ban/ban.xlsx",
        "templates/brand/brand.csv",
        "templates/category/Qoo10_CategoryInfo.csv",
        "templates/registered/registered.xlsx"
    ]
    
    missing_files = []
    for file_path in files_to_check:
        if Path(file_path).exists():
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path}")
            missing_files.append(file_path)
    
    if missing_files:
        print(f"\n⚠️  누락된 파일: {len(missing_files)}개")
        return False
    else:
        print("\n✅ 모든 필요 파일 확인됨")
        return True


def main():
    """메인 테스트 함수"""
    print("🧪 업로더 빠른 테스트 시작")
    print("=" * 60)
    
    # 1. 파일 확인
    if not check_files():
        print("\n❌ 필요한 파일이 없습니다. 먼저 파일을 준비하세요.")
        return False
    
    # 2. 테스트 데이터 생성
    if not run_command("make create-test-data", "테스트 데이터 생성"):
        return False
    
    # 3. 업로더 테스트 실행
    if not run_command("make upload-test", "업로더 테스트 실행"):
        return False
    
    # 4. 결과 확인
    print("\n📊 결과 확인")
    print("-" * 60)
    
    output_dir = Path("uploader/output")
    if output_dir.exists():
        excel_files = list(output_dir.glob("qoo10_upload_*.xlsx"))
        if excel_files:
            latest_file = max(excel_files, key=lambda p: p.stat().st_mtime)
            print(f"✅ 생성된 파일: {latest_file}")
            
            # Excel 파일 내용 간단 확인
            try:
                import pandas as pd
                df = pd.read_excel(latest_file, header=0)
                print(f"📊 데이터: {len(df)}행 x {len(df.columns)}열")
                if len(df) > 0:
                    print(f"첫 번째 상품: {df.iloc[0].get('item_name', 'N/A')}")
                else:
                    print("⚠️  데이터 행이 없음")
            except Exception as e:
                print(f"⚠️  Excel 파일 읽기 실패: {e}")
        else:
            print("❌ 생성된 Excel 파일이 없음")
            return False
    else:
        print("❌ 출력 디렉토리가 없음")
        return False
    
    print("\n✅ 테스트 완료!")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
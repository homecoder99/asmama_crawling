"""병렬 GPT 처리 테스트 스크립트.

간단한 테스트 데이터로 병렬 GPT 번역이 제대로 작동하는지 확인한다.
"""

import sys
import os
import logging
import dotenv

# 환경변수 로드
dotenv.load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# uploader 모듈 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'uploader'))

from parallel_gpt_processor import ParallelGPTProcessor, TranslationTask

def test_parallel_translation():
    """병렬 번역 테스트."""
    print("=" * 60)
    print("병렬 GPT 번역 테스트 시작 (품절 처리 개선 버전)")
    print("=" * 60)
    print()

    # 테스트 데이터 (간단한 5개 상품)
    test_products = [
        {"item_name": "[올리브영 단독] 토너패드 30매 증정 기획", "brand_name": "라운드랩"},
        {"item_name": "1+1 수분크림 50ml 특가세트", "brand_name": "닥터자르트"},
        {"item_name": "[신제품] 비타민C 세럼 30ml", "brand_name": "클리오"},
        {"item_name": "선크림 SPF50+ PA++++ 50ml", "brand_name": "라로슈포제"},
        {"item_name": "[한정판] 립틴트 세트 5종", "brand_name": "롬앤"},
    ]

    test_options = [
        "단품 200ml 16,720원",
        "세트 (50ml+30ml) 25,000원",
        "01 클리어 단품",
        "품절",
        "（품절）센시비오 H2O 850ml K2",
        "[품절] 01 베이지",
        "50mL×2개 세트",
    ]

    # 병렬 프로세서 초기화 (테스트용으로 max_concurrent=3)
    processor = ParallelGPTProcessor(
        max_concurrent=3,
        max_retries=2,
        timeout=30.0
    )

    print(f"프로세서 설정:")
    print(f"  - 동시 처리 수: {processor.max_concurrent}")
    print(f"  - 최대 재시도: {processor.max_retries}")
    print(f"  - 타임아웃: {processor.timeout}초")
    print()

    # 번역 작업 수집
    translation_tasks = []

    # 상품명 번역 작업
    for i, product in enumerate(test_products):
        translation_tasks.append(TranslationTask(
            index=i,
            task_type='product_name',
            input_text=product['item_name'],
            brand=product['brand_name']
        ))

    # 옵션 번역 작업
    for i, option in enumerate(test_options):
        translation_tasks.append(TranslationTask(
            index=i * 10000,  # 복합 인덱스
            task_type='option',
            input_text=option
        ))

    print(f"총 번역 작업 수: {len(translation_tasks)}개")
    print(f"  - 상품명: {len(test_products)}개")
    print(f"  - 옵션: {len(test_options)}개")
    print()

    # 병렬 번역 실행
    print("병렬 번역 실행 중...")
    print("-" * 60)

    import asyncio
    completed_tasks = asyncio.run(
        processor.process_batch(translation_tasks, show_progress=True)
    )

    print("-" * 60)
    print()

    # 결과 출력
    print("=" * 60)
    print("번역 결과")
    print("=" * 60)
    print()

    # 상품명 번역 결과
    print("📦 상품명 번역 결과:")
    print()
    for task in completed_tasks:
        if task.task_type == 'product_name':
            product = test_products[task.index]
            print(f"[{task.index + 1}] {product['brand_name']}")
            print(f"  원문: {task.input_text}")
            print(f"  번역: {task.result}")
            if task.error:
                print(f"  ❌ 에러: {task.error}")
            print()

    # 옵션 번역 결과
    print("🔧 옵션 번역 결과 (품절 처리 개선):")
    print()
    for task in completed_tasks:
        if task.task_type == 'option':
            option_idx = task.index // 10000
            print(f"[{option_idx + 1}]")
            print(f"  원문: {task.input_text}")
            print(f"  번역: {task.result if task.result else '(빈 문자열)'}")
            if task.error:
                print(f"  ❌ 에러: {task.error}")
            print()

    # 통계
    print("=" * 60)
    print("통계")
    print("=" * 60)
    total = len(completed_tasks)
    success = sum(1 for task in completed_tasks if not task.error)
    failed = total - success

    print(f"총 작업: {total}개")
    print(f"성공: {success}개 ({success/total*100:.1f}%)")
    print(f"실패 (에러): {failed}개")
    print()

    # 품절 옵션 처리 확인
    soldout_options = [
        task for task in completed_tasks 
        if task.task_type == 'option' and '품절' in task.input_text
    ]
    print("품절 옵션 처리 확인:")
    for task in soldout_options:
        option_idx = task.index // 10000
        is_empty = not task.result or task.result.strip() == ''
        status = "✅ (품절 단어만)" if not is_empty and '품절' not in task.result else "✅ (빈 문자열)" if is_empty else "❌"
        print(f"  [{option_idx + 1}] {status}")
        print(f"      원문: {task.input_text}")
        print(f"      번역: '{task.result}'")

    if failed == 0:
        print("\n✅ 모든 번역이 성공적으로 완료되었습니다!")
    else:
        print(f"\n⚠️  {failed}개의 번역 실패가 있습니다.")

    return failed == 0


if __name__ == "__main__":
    try:
        success = test_parallel_translation()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n테스트가 사용자에 의해 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 테스트 실행 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

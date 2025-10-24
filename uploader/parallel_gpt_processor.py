"""GPT API 병렬 처리 유틸리티.

OpenAI API 호출을 비동기 병렬로 처리하여 대량의 번역 작업을 빠르게 수행한다.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
from openai import AsyncOpenAI
from tqdm import tqdm


@dataclass
class TranslationTask:
    """번역 작업 정보."""
    index: int
    task_type: str  # 'product_name' or 'option'
    input_text: str
    brand: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None


class ParallelGPTProcessor:
    """
    GPT API 호출을 병렬로 처리하는 클래스.

    특징:
    - asyncio 기반 비동기 병렬 처리
    - 동시 요청 수 제한 (rate limit 준수)
    - 진행률 표시
    - 에러 핸들링 및 재시도
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        max_retries: int = 3,
        timeout: float = 30.0
    ):
        """
        ParallelGPTProcessor 초기화.

        Args:
            max_concurrent: 동시 처리할 최대 요청 수 (기본: 10)
            max_retries: 실패 시 재시도 횟수 (기본: 3)
            timeout: 요청 타임아웃 (초, 기본: 30.0)
        """
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)

        # OpenAI 클라이언트 (비동기)
        self.client = AsyncOpenAI()

    async def _translate_product_name(
        self,
        task: TranslationTask,
        semaphore: asyncio.Semaphore
    ) -> TranslationTask:
        """
        상품명 번역 (비동기).

        Args:
            task: 번역 작업
            semaphore: 동시 요청 수 제한용 세마포어

        Returns:
            완료된 작업
        """
        async with semaphore:
            for attempt in range(self.max_retries):
                try:
                    response = await asyncio.wait_for(
                        self.client.responses.create(
                            model="gpt-5-mini",
                            input=f"""You are a KO→JA e-commerce product-title localizer.

## GOAL
Translate the Korean product name into natural Japanese **product name only**.
- Delete brand names and any promotional or packaging info.
- Output **Japanese only**, a single line, no quotes/brackets/extra words.

## REMOVE (ALWAYS)
1) Brand: remove every appearance of the given brand (and its Japanese/English forms if present).
2) Bracketed segments: delete text inside any of these and the brackets themselves:
   [], ［］, (), （）, {{}}, 「」, 『』, 【】, 〈〉, 《》, <>.
   - If a bracket contains only essential spec like capacity/size/shade (e.g., 50mL, 01, 1.5), keep the info **without brackets**.
3) Promo words (KO): 기획, 증정, 이벤트, 한정, 한정판, 특가, 세트, 1+1, 2+1, 덤, 사은품, 무료, 할인,
   출시, 런칭, 론칭, 신제품, 리뉴얼, 업그레이드, 패키지, 기념, 컬렉션, 에디션, 올리브영,
   단독, 독점, 먼저, 최초, 브랜드명, 픽, 추천, 콜라보, 선택, 단품, 더블, 증량.

## STYLE
- Noun phrase only, no sentence form. No emojis, no decorative symbols.
- Do **not** invent information. If unsure, omit.

## OUTPUT
Return **one line** with the final Japanese product name.
Do not include explanations, quotes, or any non-Japanese text.

--------------------------------
BRAND (to remove): {task.brand}
KOREAN_NAME: {task.input_text}
"""
                        ),
                        timeout=self.timeout
                    )

                    task.result = response.output_text.strip()
                    return task

                except asyncio.TimeoutError:
                    self.logger.warning(f"Timeout on attempt {attempt + 1}/{self.max_retries} for: {task.input_text[:50]}")
                    if attempt == self.max_retries - 1:
                        task.error = "Timeout after all retries"
                        task.result = task.input_text  # 실패 시 원문 반환
                    await asyncio.sleep(1)

                except Exception as e:
                    self.logger.error(f"Error on attempt {attempt + 1}/{self.max_retries}: {str(e)}")
                    if attempt == self.max_retries - 1:
                        task.error = str(e)
                        task.result = task.input_text  # 실패 시 원문 반환
                    await asyncio.sleep(1)

        return task

    async def _translate_option(
        self,
        task: TranslationTask,
        semaphore: asyncio.Semaphore
    ) -> TranslationTask:
        """
        옵션 번역 (비동기).

        Args:
            task: 번역 작업
            semaphore: 동시 요청 수 제한용 세마포어

        Returns:
            완료된 작업
        """
        async with semaphore:
            for attempt in range(self.max_retries):
                try:
                    response = await asyncio.wait_for(
                        self.client.responses.create(
                            model="gpt-5-mini",
                            input=f"""You are a KO→JA e-commerce option translator.

## GOAL
Translate the option text into a clean **Japanese option name only** (single line).
- Output **Japanese only** (no Korean). Use katakana for names if needed.
- **Never include price** (e.g., 16,720원).
- **Remove sold-out indicators** (품절/일시품절/재고없음/매진/완판/out of stock) but **translate the rest**.

## WHAT TO KEEP (for option segmentation)
Keep information that defines the option itself:
- **Sale form**: 단품, 세트, ×N개 / N개 세트 / 2개 세트 / 본체+리필 / 50mL+30mL
- **Capacity/size/count**: 120mL, 12g, 3매, 2개, 01/02/003 (숫자 단위와 mL/g/매/개）
- **Type/color/shade/model names**: 00 클리어, 03 로지, 센시비오 H2O 850mL K2
- **Promo that defines composition only** (option-defining): 1+1, 2+1, 증량 +10mL（내용이 구성요소와 명확한 경우）
Do NOT keep marketing claims (인기/No.1/한정기념 등).

## WHAT TO REMOVE
- **Sold-out indicators**: 품절, 일시품절, 재고없음, 매진, 완판, out of stock (remove but translate rest)
- Store codes / metadata: strings like `Option1||*`, `||*0||*200||*...`, `oliveyoung_A...`, SKU/ID hashes
- Bracketed non-structural claims: [ ], ［ ］, ( ), （ ）, 【 】, 〈 〉, 《 》, 「 」, 『 』 **장식문구**。
  ※ 다만、용량 또는 성분（50mL+30mL、본체+리필）**실제 구성**은 남깁니다（괄호는 제거하고 내용만 남깁니다）。
- Any currency or price-like tokens（44,100원, 36,550KRW）

## NORMALIZATION
- Half-width numbers; units as **mL/g**; use **×** for multiplicative counts; use **+** for bundles: `30mL+30mL`, `7mL×3`
- Convert Hangul words to standard JP EC terms: 단품→単品 / 세트→セット / 증정→おまけ / 추가→追加 / 리필→リフィル
- Keep original attribute order **when reasonable**, but ensure readability (spaces between tokens).

## OUTPUT
Return **only** the final Japanese option string on one line.
No explanations, no quotes, no brackets unless part of model numbers (e.g., "01" without brackets).
**If only sold-out indicator remains after processing, return empty string.**

--------------------------------
OPTION_INPUT: {task.input_text}

# Examples
- IN: `Option2||*03 로지 16,720원` → OUT: `03 ロージー`
- IN: `（품절）센시비오 H2O 850ml K2` → OUT: `센시비오 H2O 850mL K2`
- IN: `품절` → OUT: ``  (empty string - only sold-out indicator)
- IN: `단품 200ml` → OUT: `単品 200mL`
- IN: `30ml+30ml` → OUT: `30mL+30mL`
- IN: `크림 50mL 단품` → OUT: `クリーム 50mL 単品`
- IN: `1+1 50ml` → OUT: `1+1 50mL`
- IN: `본체+리필 12g` → OUT: `本体+リフィル 12g`
- IN: `[품절] 01 베이지` → OUT: `01 ベージュ`
"""
                        ),
                        timeout=self.timeout
                    )

                    task.result = response.output_text.strip()
                    return task

                except asyncio.TimeoutError:
                    self.logger.warning(f"Timeout on attempt {attempt + 1}/{self.max_retries} for option: {task.input_text[:50]}")
                    if attempt == self.max_retries - 1:
                        task.error = "Timeout after all retries"
                        task.result = ""
                    await asyncio.sleep(1)

                except Exception as e:
                    self.logger.error(f"Error on attempt {attempt + 1}/{self.max_retries}: {str(e)}")
                    if attempt == self.max_retries - 1:
                        task.error = str(e)
                        task.result = ""
                    await asyncio.sleep(1)

        return task

    async def process_batch(
        self,
        tasks: List[TranslationTask],
        show_progress: bool = True
    ) -> List[TranslationTask]:
        """
        번역 작업을 병렬로 처리한다.

        Args:
            tasks: 번역 작업 목록
            show_progress: 진행률 표시 여부

        Returns:
            완료된 작업 목록
        """
        if not tasks:
            return []

        semaphore = asyncio.Semaphore(self.max_concurrent)

        # 작업 타입별로 적절한 함수 선택
        async def process_task(task: TranslationTask) -> TranslationTask:
            if task.task_type == 'product_name':
                return await self._translate_product_name(task, semaphore)
            elif task.task_type == 'option':
                return await self._translate_option(task, semaphore)
            else:
                task.error = f"Unknown task type: {task.task_type}"
                return task

        # 병렬 실행
        if show_progress:
            results = []
            with tqdm(total=len(tasks), desc="번역 진행") as pbar:
                for coro in asyncio.as_completed([process_task(task) for task in tasks]):
                    result = await coro
                    results.append(result)
                    pbar.update(1)
            return results
        else:
            return await asyncio.gather(*[process_task(task) for task in tasks])

    def process_batch_sync(
        self,
        tasks: List[TranslationTask],
        show_progress: bool = True
    ) -> List[TranslationTask]:
        """
        동기 인터페이스로 배치 처리 (내부적으로 비동기 실행).

        Args:
            tasks: 번역 작업 목록
            show_progress: 진행률 표시 여부

        Returns:
            완료된 작업 목록
        """
        return asyncio.run(self.process_batch(tasks, show_progress))


def translate_product_names_parallel(
    products: List[Dict[str, Any]],
    name_key: str = "item_name",
    brand_key: str = "brand_name",
    max_concurrent: int = 10
) -> List[str]:
    """
    상품명들을 병렬로 번역한다.

    Args:
        products: 상품 목록
        name_key: 상품명 키
        brand_key: 브랜드명 키
        max_concurrent: 동시 처리 수

    Returns:
        번역된 상품명 목록
    """
    processor = ParallelGPTProcessor(max_concurrent=max_concurrent)

    # 작업 생성
    tasks = [
        TranslationTask(
            index=i,
            task_type='product_name',
            input_text=str(product.get(name_key, '')),
            brand=str(product.get(brand_key, ''))
        )
        for i, product in enumerate(products)
        if product.get(name_key)
    ]

    # 병렬 처리
    completed_tasks = processor.process_batch_sync(tasks)

    # 결과 추출
    return [task.result for task in sorted(completed_tasks, key=lambda t: t.index)]


def translate_options_parallel(
    options: List[str],
    max_concurrent: int = 10
) -> List[str]:
    """
    옵션들을 병렬로 번역한다.

    Args:
        options: 옵션 목록
        max_concurrent: 동시 처리 수

    Returns:
        번역된 옵션 목록
    """
    processor = ParallelGPTProcessor(max_concurrent=max_concurrent)

    # 작업 생성
    tasks = [
        TranslationTask(
            index=i,
            task_type='option',
            input_text=option
        )
        for i, option in enumerate(options)
        if option
    ]

    # 병렬 처리
    completed_tasks = processor.process_batch_sync(tasks)

    # 결과 추출
    return [task.result for task in sorted(completed_tasks, key=lambda t: t.index)]

"""이미지 전처리 및 품질 검사 시스템.

Claude Vision API를 사용하여 이미지 품질을 분석하고
대표 이미지를 선정하는 시스템을 구현한다.
"""

import os
import json
import textwrap
from typing import Dict, Any
import logging
import anthropic
import dotenv
import requests
from PIL import Image
import numpy as np
from io import BytesIO

# 환경변수 로드
dotenv.load_dotenv()

class ImageProcessor:
    """
    이미지 전처리 및 품질 검사 담당 클래스.
    
    Claude Vision API를 사용하여 쿠팡 상품 이미지 규칙에 맞는
    이미지를 필터링하고 대표 이미지를 선정한다.
    """
    
    def __init__(self, filter_mode: str = "none", site: str = "asmama"):
        """
        ImageProcessor 초기화.

        Args:
            filter_mode: 필터링 모드 ("none", "ai", "advanced", "both")
                - "none": 필터링 없음 (모든 이미지 통과) - 기본값
                - "ai": Claude Vision API만 사용
                - "advanced": 고급 로직 필터링만 사용
                - "both": 두 방법 모두 사용
            site: 사이트 타입 ("asmama", "oliveyoung")
        """
        self.logger = logging.getLogger(__name__)
        self.filter_mode = filter_mode
        self.site = site

        # Claude 클라이언트 (AI 모드일 때만 초기화)
        if filter_mode in ["ai", "both"]:
            self.client = anthropic.Anthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY")
            )
        else:
            self.client = None
        
        # 쿠팡 상품 이미지 규칙 프롬프트
        self.rules_prompt = textwrap.dedent("""
            You are a **Product-Image Compliance Bot**.  
            For every image you receive, evaluate it against the 8 rules below and answer **only** with a compact JSON object(No Markdown):

            JSON Format:
            {
            "rule1": {"result": "PASS|FAIL|UNCERTAIN", "reason": "< ≤25 chars>"},
            "rule2": {"result": "PASS|FAIL|UNCERTAIN", "reason": "< ≤25 chars>"},
            "rule3": {"result": "PASS|FAIL|UNCERTAIN", "reason": "< ≤25 chars>"},
            "rule4": {"result": "PASS|FAIL|UNCERTAIN", "reason": "< ≤25 chars>"},
            "rule5": {"result": "PASS|FAIL|UNCERTAIN", "reason": "< ≤25 chars>"},
            "rule6": {"result": "PASS|FAIL|UNCERTAIN", "reason": "< ≤25 chars>"},
            "rule7": {"result": "PASS|FAIL|UNCERTAIN", "reason": "< ≤25 chars>"},
            "rule8": {"result": "PASS|FAIL|UNCERTAIN", "reason": "< ≤25 chars>"}
            }

            If unsure or unknown, return "UNCERTAIN". No extra keys, no commentary.

            ───────────────────────────────
            RULES (Coupang Main-Image v2)
            ───────────────────────────────
            1. Main product's longest side ≥ 80 % of image's shorter side.
            2. ❌ NO added text / icons / stickers / watermarks.  
            ✅ Text printed on the product or its retail package **is allowed**.
            3. Product is centered: bounding-box center within ±10 % of image center.
            4. Background must be plain white or near-white → LAB L≥95 and |a|,|b|≤3.  
            Soft natural shadow OK; colored backdrops ❌.
            5. Show **only** items included in the sales unit.  
            • Multi-pack or set? Photograph all pieces together.  
            • Extra props or unrelated items → FAIL.
            6. NO collage, split frames, duplicate angles, or graphic composites.  
            Single photographic capture only.
            7. NO freebies / "gift" items / promotional add-ons in the main image.
            8. Photograph must show the product's **front view** (≤15° yaw).

            Clarifications & heuristics
            • Multi-item vs collage: check lighting consistency, shared shadows, contiguous edges.  
            • Overlay text detection: any OCR hit not physically part of the product/package → FAIL.  
            • "Near-white" background: allow #F8F8F8–#FFFFFF region; evaluate average & variance.  
            • If the product is transparent, ignore background bleed when judging Rule 2 & 5.
            ───────────────────────────────
        """).strip()
        
        # 이미지 품질 기준
        self.max_images_per_product = 10  # 상품당 최대 이미지 수
        self.min_pass_rules = 6  # 최소 통과해야 할 규칙 수 (완화: 6/8)
        
        # 사이트별 고급 필터링 파라미터 설정
        self._set_site_parameters(site)
        
        # 이미지 다운로드용 세션 생성
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    
    def _set_site_parameters(self, site: str):
        """
        사이트별 고급 필터링 파라미터를 설정한다.
        
        Args:
            site: 사이트 타입 ("asmama", "oliveyoung")
        """
        if site == "asmama":
            # Asmama 파라미터 (기존 설정)
            self.border_threshold = 180  # 테두리 흰색 임계값 (베이지 배경 대응)
            self.border_ratio = 0.05  # 테두리 영역 비율 (완화)
            self.white_threshold = 180  # 흰색 픽셀 임계값 (베이지 배경 대응)
            self.center_white_max = 0.98  # 중앙 영역 허용 최대 흰색 비율 (상품 중심)
            self.outside_white_min = 0.2  # 외곽 영역 허용 최소 흰색 비율 (베이지 배경)
            
            # Asmama 전용 파라미터
            self.measure_white_threshold = 230
            self.border_check_threshold = 240
            self.border_check_ratio = 0.1
            self.border_pass_threshold = 0.9  # 90% 이상만 흰색이면 통과
            self.center_outside_threshold = 220
            
        elif site == "oliveyoung":
            # Oliveyoung 파라미터 (새로운 설정)
            self.border_threshold = 250  # 더 엄격한 흰색 기준
            self.border_ratio = 0.1  # 표준 테두리 영역 비율
            self.white_threshold = 230  # 표준 흰색 픽셀 임계값
            self.center_white_max = 0.95  # 중앙 영역 허용 최대 흰색 비율
            self.outside_white_min = 0.3  # 외곽 영역 허용 최소 흰색 비율
            
            # Oliveyoung 전용 파라미터
            self.measure_white_threshold = 230
            self.border_check_threshold = 250
            self.border_check_ratio = 0.1
            self.border_pass_threshold = 0.9  # 1-n (90%) 기준
            self.center_outside_threshold = 230
            
        else:
            # 기본값 (asmama와 동일)
            self.border_threshold = 180
            self.border_ratio = 0.05
            self.white_threshold = 180
            self.center_white_max = 0.98
            self.outside_white_min = 0.2
            
            self.measure_white_threshold = 230
            self.border_check_threshold = 240
            self.border_check_ratio = 0.1
            self.border_pass_threshold = 0.9
            self.center_outside_threshold = 220
        
        self.logger.info(f"{site.capitalize()} 사이트 파라미터 설정 완료")
    
    def check_product_image(self, url: str) -> Dict[str, Any]:
        """
        단일 이미지의 규칙 준수 여부를 검사한다.
        
        Args:
            url: 검사할 이미지 URL
            
        Returns:
            규칙 검사 결과
        """
        try:
            response = self.client.messages.create(
                model="claude-3-7-sonnet-20250219",
                max_tokens=300,
                temperature=0,
                system=self.rules_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Evaluate this image."},
                            {"type": "image", "source": {"type": "url", "url": url}},
                        ],
                    },
                ],
            )
            
            result_json = response.content[0].text
            return json.loads(result_json)

        except (ValueError, json.JSONDecodeError) as e:
            self.logger.warning(f"JSON 파싱 실패: {url} - {str(e)}")
            # JSON 블록 추출 시도
            try:
                cleaned_json = self._extract_json_from_response(result_json)
                if cleaned_json:
                    return json.loads(cleaned_json)
            except:
                pass
            
            # 재시도 1회
            try:
                response = self.client.messages.create(
                    model="claude-3-7-sonnet-20250219",
                    max_tokens=300,
                    temperature=0,
                    system=self.rules_prompt,
                    messages=[
                        {
                            "role": "user", 
                            "content": [
                                {"type": "text", "text": "Evaluate this image."},
                                {"type": "image", "source": {"type": "url", "url": url}},
                            ],
                        },
                    ],
                )
                result_json = response.content[0].text
                return json.loads(result_json)
            except Exception as retry_error:
                self.logger.error(f"재시도 실패: {url} - {str(retry_error)}")
                return {
                    f"rule{i}": {"result": "FAIL", "reason": "파싱 실패"}
                    for i in range(1, 9)
                }
        except Exception as e:
            self.logger.error(f"이미지 규칙 검사 실패: {url} - {str(e)}")
            # 실패 시 모든 규칙을 FAIL으로 설정
            return {
                f"rule{i}": {"result": "FAIL", "reason": "분석 실패"}
                for i in range(1, 9)
            }
    
    def _download_image(self, url: str) -> Image.Image:
        """
        URL에서 이미지를 다운로드하여 PIL Image로 반환한다.
        
        Args:
            url: 이미지 URL
            
        Returns:
            PIL Image 객체
        """
        try:
            # 403 Forbidden 에러 방지를 위한 헤더 설정
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'image',
                'Sec-Fetch-Mode': 'no-cors',
                'Sec-Fetch-Site': 'cross-site',
            }
            
            # URL의 도메인에 따라 Referer 헤더 추가
            if 'asmama.com' in url:
                headers['Referer'] = 'http://www.asmama.com/'
            elif 'oliveyoung.co.kr' in url:
                headers['Referer'] = 'https://www.oliveyoung.co.kr/'
            elif 'coupang.com' in url:
                headers['Referer'] = 'https://www.coupang.com/'
            
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            return Image.open(BytesIO(response.content)).convert("RGB")
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                # 403 에러 시 다른 User-Agent로 재시도
                self.logger.warning(f"403 에러 발생, 다른 User-Agent로 재시도: {url}")
                try:
                    fallback_headers = {
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
                        'Accept': '*/*',
                        'Accept-Language': 'ko-KR,ko;q=0.9',
                        'Cache-Control': 'no-cache',
                        'Pragma': 'no-cache',
                    }
                    
                    if 'asmama.com' in url:
                        fallback_headers['Referer'] = 'http://www.asmama.com/'
                    
                    response = requests.get(url, headers=fallback_headers, timeout=15)
                    response.raise_for_status()
                    return Image.open(BytesIO(response.content)).convert("RGB")
                except Exception as retry_error:
                    self.logger.error(f"재시도 실패: {url} - {str(retry_error)}")
                    raise
            else:
                raise
                
        except Exception as e:
            self.logger.error(f"이미지 다운로드 실패: {url} - {str(e)}")
            raise
    
    def _measure_white_ratio_in_region(self, img: Image.Image, x1: int, y1: int, x2: int, y2: int, threshold: int = None) -> float:
        """
        이미지의 특정 영역에서 흰색 픽셀의 비율을 측정한다.
        
        Args:
            img: 분석할 이미지 객체
            x1, y1, x2, y2: 영역 좌표
            threshold: 흰색 판정 임계값
            
        Returns:
            흰색 픽셀의 비율 (0.0 ~ 1.0)
        """
        try:
            if threshold is None:
                threshold = self.measure_white_threshold
                
            cropped = img.crop((x1, y1, x2, y2))
            pixels = np.array(cropped)
            if len(pixels.shape) != 3 or pixels.shape[2] != 3:
                return 0.0

            total = pixels.shape[0] * pixels.shape[1]
            white = np.sum(
                (pixels[:, :, 0] >= threshold) &
                (pixels[:, :, 1] >= threshold) &
                (pixels[:, :, 2] >= threshold)
            )
            return white / total if total > 0 else 0.0
        except Exception:
            return 0.0
    
    def _check_border_white(self, img: Image.Image, n: float = None, threshold: int = None) -> bool:
        """
        이미지의 테두리 영역이 충분히 흰색인지 확인한다.
        
        Args:
            img: 검사할 이미지 객체
            n: 테두리 영역의 비율
            threshold: 흰색 판정 임계값
            
        Returns:
            모든 테두리 영역이 충분히 흰색이면 True
        """
        try:
            if n is None:
                n = self.border_check_ratio
            if threshold is None:
                threshold = self.border_check_threshold
                
            w, h = img.size
            if w < 10 or h < 10:
                return False
            
            x_th = int(n * w)
            y_th = int(n * h)

            top = self._measure_white_ratio_in_region(img, 0, 0, w, y_th, threshold)
            bottom = self._measure_white_ratio_in_region(img, 0, h - y_th, w, h, threshold)
            left = self._measure_white_ratio_in_region(img, 0, 0, x_th, h, threshold)
            right = self._measure_white_ratio_in_region(img, w - x_th, 0, w, h, threshold)

            # 사이트별 기준 적용
            if self.site == "oliveyoung":
                # Oliveyoung: 1-n 기준
                return all(r >= 1 - n for r in [top, bottom, left, right])
            else:
                # Asmama: 고정 90% 기준
                return all(r >= self.border_pass_threshold for r in [top, bottom, left, right])
        except Exception:
            return False
    
    def _measure_center_outside_white_ratio(self, img: Image.Image, threshold: int = None) -> tuple:
        """
        이미지의 중앙 영역과 외곽 영역의 흰색 픽셀 비율을 측정한다.
        
        Args:
            img: 분석할 이미지 객체
            threshold: 흰색 판정 임계값
            
        Returns:
            (중앙 영역 흰색 비율, 외곽 영역 흰색 비율)
        """
        try:
            if threshold is None:
                threshold = self.center_outside_threshold
                
            w, h = img.size
            x1, x2 = int(0.3 * w), int(0.7 * w)
            y1, y2 = int(0.3 * h), int(0.7 * h)

            center_ratio = self._measure_white_ratio_in_region(img, x1, y1, x2, y2, threshold)

            pixels = np.array(img)
            total_pixels = pixels.shape[0] * pixels.shape[1]
            total_white = np.sum((pixels[:, :, 0] >= threshold) & 
                                 (pixels[:, :, 1] >= threshold) & 
                                 (pixels[:, :, 2] >= threshold))

            center_cropped = pixels[y1:y2, x1:x2, :]
            center_white = np.sum((center_cropped[:, :, 0] >= threshold) &
                                  (center_cropped[:, :, 1] >= threshold) &
                                  (center_cropped[:, :, 2] >= threshold))

            outside_pixels = total_pixels - (x2 - x1) * (y2 - y1)
            outside_white = total_white - center_white

            outside_ratio = outside_white / outside_pixels if outside_pixels > 0 else 0.0

            return center_ratio, outside_ratio
        except Exception:
            return 0.0, 0.0
    
    def _advanced_image_filter(self, url: str) -> Dict[str, Any]:
        """
        고급 이미지 필터링을 수행한다 (테두리 검사 + 흰색 비율 검사).
        
        Args:
            url: 이미지 URL
            
        Returns:
            필터링 결과 딕셔너리
        """
        try:
            img = self._download_image(url)
            
            # 1. 테두리 검사
            border_ok = self._check_border_white(
                img, 
                n=self.border_ratio, 
                threshold=self.border_threshold
            )
            
            # 2. 중앙/외곽 흰색 비율 검사
            center_ratio, outside_ratio = self._measure_center_outside_white_ratio(
                img, 
                threshold=self.white_threshold
            )
            
            # 3. 종합 판정 (완화된 기준)
            white_ratio_ok = (center_ratio <= self.center_white_max and 
                             outside_ratio >= self.outside_white_min)
            
            return {
                "passed": border_ok and white_ratio_ok,
                "border_ok": border_ok,
                "white_ratio_ok": white_ratio_ok,
                "center_ratio": center_ratio,
                "outside_ratio": outside_ratio,
                "filter_reason": self._get_filter_reason(border_ok, white_ratio_ok, center_ratio, outside_ratio)
            }
            
        except Exception as e:
            self.logger.warning(f"고급 필터링 실패: {url} - {str(e)}")
            # 실패 시 통과로 처리 (기존 필터링에만 의존)
            return {
                "passed": True,
                "border_ok": True,
                "white_ratio_ok": True,
                "center_ratio": 0.0,
                "outside_ratio": 1.0,
                "filter_reason": "필터링 오류로 통과 처리"
            }
    
    def _get_filter_reason(self, border_ok: bool, white_ratio_ok: bool, center_ratio: float, outside_ratio: float) -> str:
        """
        필터링 사유를 생성한다.
        
        Returns:
            필터링 사유 문자열
        """
        if not border_ok and not white_ratio_ok:
            return f"테두리 불량 + 흰색비율 불량(중앙:{center_ratio:.2f}/외곽:{outside_ratio:.2f})"
        elif not border_ok:
            return "테두리 영역이 충분히 흰색이 아님"
        elif not white_ratio_ok:
            return f"흰색 비율 불량(중앙:{center_ratio:.2f}/외곽:{outside_ratio:.2f})"
        else:
            return f"통과(중앙:{center_ratio:.2f}/외곽:{outside_ratio:.2f})"
    
    def _filter_with_ai_only(self, url: str) -> Dict[str, Any]:
        """
        Claude Vision API만 사용하여 필터링한다.
        """
        try:
            rules_result = self.check_product_image(url)
            pass_count = sum(1 for rule_data in rules_result.values() 
                           if rule_data.get("result") == "PASS")
            compliance_score = pass_count / 8.0
            
            passed = pass_count >= self.min_pass_rules
            
            return {
                "url": url,
                "passed": passed,
                "compliance_score": compliance_score,
                "rules_result": rules_result,
                "reason": f"AI 검사: {pass_count}/8 규칙 통과"
            }
        except Exception as e:
            self.logger.error(f"AI 필터링 실패: {url} - {str(e)}")
            return {"url": url, "passed": False, "compliance_score": 0.0, "reason": "AI 검사 실패"}
    
    def _filter_with_advanced_only(self, url: str) -> Dict[str, Any]:
        """
        고급 로직만 사용하여 필터링한다.
        """
        try:
            advanced_filter = self._advanced_image_filter(url)
            
            return {
                "url": url,
                "passed": advanced_filter["passed"],
                "compliance_score": 1.0 if advanced_filter["passed"] else 0.0,
                "advanced_filter": advanced_filter,
                "reason": advanced_filter["filter_reason"]
            }
        except Exception as e:
            self.logger.error(f"고급 필터링 실패: {url} - {str(e)}")
            return {"url": url, "passed": False, "compliance_score": 0.0, "reason": "고급 필터링 실패"}
    
    def _filter_with_both(self, url: str) -> Dict[str, Any]:
        """
        두 방법을 모두 사용하여 필터링한다 (고급 로직 먼저, 통과 시 AI 검사).
        """
        try:
            # 1. 고급 필터링 (빠른 사전 필터링)
            advanced_filter = self._advanced_image_filter(url)
            
            if not advanced_filter["passed"]:
                return {
                    "url": url,
                    "passed": False,
                    "compliance_score": 0.0,
                    "advanced_filter": advanced_filter,
                    "reason": f"고급 필터링 탈락: {advanced_filter['filter_reason']}"
                }
            
            # 2. AI 검사 (고급 필터링 통과 시)
            rules_result = self.check_product_image(url)
            pass_count = sum(1 for rule_data in rules_result.values() 
                           if rule_data.get("result") == "PASS")
            compliance_score = pass_count / 8.0
            
            # 고급 필터링 보너스 점수
            advanced_bonus = 0.1 if (advanced_filter["center_ratio"] <= 0.5 and 
                                   advanced_filter["outside_ratio"] >= 0.8) else 0.0
            final_score = compliance_score + advanced_bonus
            
            passed = pass_count >= self.min_pass_rules
            
            return {
                "url": url,
                "passed": passed,
                "compliance_score": final_score,
                "rules_result": rules_result,
                "advanced_filter": advanced_filter,
                "reason": f"통합 검사: AI {pass_count}/8 + {advanced_filter['filter_reason']}"
            }
            
        except Exception as e:
            self.logger.error(f"통합 필터링 실패: {url} - {str(e)}")
            return {"url": url, "passed": False, "compliance_score": 0.0, "reason": "통합 필터링 실패"}

    def _extract_json_from_response(self, response_text: str) -> str:
        """
        응답 텍스트에서 JSON 부분만 추출한다.
        
        Args:
            response_text: 원본 응답 텍스트
            
        Returns:
            추출된 JSON 문자열 또는 빈 문자열
        """
        try:
            # { } 블록 찾기
            start_index = response_text.find('{')
            if start_index == -1:
                return ""
            
            # 매칭되는 } 찾기
            brace_count = 0
            for i, char in enumerate(response_text[start_index:], start_index):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        return response_text[start_index:i+1]
            
            return ""
        except Exception:
            return ""
    
    def process_product_images(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        상품의 모든 이미지를 처리한다.
        
        Args:
            product_data: 상품 데이터 (images 필드 포함)
            
        Returns:
            처리된 상품 데이터 (filtered_images, representative_image 필드 추가)
        """
        images_str = product_data.get("images", "")
        if not images_str:
            product_id = product_data.get('branduid') or product_data.get('goods_no', 'unknown')
            self.logger.warning(f"이미지가 없는 상품: {product_id}")
            product_data["alternative_images"] = ""
            product_data["representative_image"] = ""
            return product_data
        
        # 이미지 URL 분리 ($$로 구분)
        image_urls = [url.strip() for url in images_str.split("$$") if url.strip()]
        
        if not image_urls:
            product_data["alternative_images"] = ""
            product_data["representative_image"] = ""
            return product_data
        
        try:
            # 필터링 모드에 따라 다른 검사 수행
            compliant_images = []

            # filter_mode가 "none"이면 모든 이미지 통과
            if self.filter_mode == "none":
                product_id = product_data.get('branduid') or product_data.get('goods_no', 'unknown')
                self.logger.info(f"이미지 필터링 비활성화: {product_id} - {len(image_urls)}개 이미지 모두 통과")

                # 모든 이미지를 그대로 사용
                for idx, url in enumerate(image_urls[:self.max_images_per_product]):
                    compliant_images.append({
                        "url": url,
                        "passed": True,
                        "compliance_score": 100 - idx,  # 순서대로 점수 부여
                        "reason": "필터링 비활성화"
                    })
            else:
                # 필터링 활성화된 경우
                for url in image_urls[:self.max_images_per_product]:
                    if self.filter_mode == "ai":
                        # AI만 사용
                        result = self._filter_with_ai_only(url)
                    elif self.filter_mode == "advanced":
                        # 고급 로직만 사용
                        result = self._filter_with_advanced_only(url)
                    else:  # "both"
                        # 두 방법 모두 사용
                        result = self._filter_with_both(url)

                    if result and result["passed"]:
                        compliant_images.append(result)
                        self.logger.info(f"이미지 통과: {url} - {result.get('reason', '')}")
                    else:
                        self.logger.warning(f"이미지 필터링 탈락: {url} - {result.get('reason', '알 수 없는 이유') if result else '처리 실패'}")
            
            # 컴플라이언스 점수 기준으로 정렬
            compliant_images.sort(key=lambda x: x["compliance_score"], reverse=True)
            
            # 최대 개수만큼 선택
            selected_images = compliant_images[:self.max_images_per_product]
            
            # 결과 업데이트
            if selected_images:
                filtered_urls = [img["url"] for img in selected_images]
                product_data["representative_image"] = selected_images[0]["url"]  # 가장 높은 점수의 이미지
                product_data["alternative_images"] = "$$".join(filtered_urls[1:]) # 대표 이미지 외 추가 이미지

                product_id = product_data.get('branduid') or product_data.get('goods_no', 'unknown')
                self.logger.info(f"이미지 처리 완료: {product_id} - {len(image_urls)}개 → {len(selected_images)}개")
            else:
                product_data["alternative_images"] = ""
                product_data["representative_image"] = ""
                product_id = product_data.get('branduid') or product_data.get('goods_no', 'unknown')
                self.logger.warning(f"규칙 통과 이미지 없음: {product_id}")
            
            return product_data
            
        except Exception as e:
            product_id = product_data.get('branduid') or product_data.get('goods_no', 'unknown')
            self.logger.error(f"이미지 처리 실패: {product_id} - {str(e)}")

            product_data["alternative_images"] = ""
            product_data["representative_image"] = ""
            return product_data


# 테스트 함수
def test_image_processor():
    """
    ImageProcessor 테스트 함수.
    """
    processor = ImageProcessor()
    
    # 테스트 이미지 URL
    test_url = "https://image.oliveyoung.co.kr/cfimages/cf-goods/uploads/images/thumbnails/550/10/0000/0017/A00000017245313ko.jpg?l=ko"
    
    # 단일 이미지 검사
    result = processor.check_product_image(test_url)
    print("이미지 규칙 검사 결과:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 상품 데이터로 전체 프로세스 테스트
    test_product = {
        "branduid": "test123",
        "item_name": "테스트 상품",
        "images": test_url
    }
    
    processed = processor.process_product_images(test_product)
    print("\n처리된 상품 데이터:")
    print(f"원본 이미지: {test_product['images']}")
    print(f"필터링된 이미지: {processed.get('filtered_images', '')}")
    print(f"대표 이미지: {processed.get('representative_image', '')}")


if __name__ == "__main__":
    test_image_processor()
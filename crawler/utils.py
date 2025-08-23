"""크롤러 유틸리티 함수 모음."""

import asyncio
import logging
import random
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# 로그 디렉토리 생성
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


def setup_logger(name: str, level: int = None) -> logging.Logger:
    """
    로거를 설정하고 반환한다.
    
    Args:
        name: 로거 이름
        level: 로그 레벨 (None이면 환경변수 LOG_LEVEL 또는 기본값 INFO 사용)
        
    Returns:
        설정된 로거 인스턴스
    """
    logger = logging.getLogger(name)
    
    # 이미 핸들러가 있으면 중복 설정 방지
    if logger.handlers:
        return logger
    
    # 로그 레벨 결정 (우선순위: 파라미터 > 환경변수 > 기본값)
    if level is None:
        log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        level = level_map.get(log_level_str, logging.INFO)
        
    logger.setLevel(level)
    
    # 로그 파일 핸들러
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_handler = logging.FileHandler(
        LOGS_DIR / f"crawl_{timestamp}.log",
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    
    # 포맷터
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 핸들러 추가
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def get_random_user_agent() -> str:
    """
    랜덤 User-Agent를 반환한다.
    
    Returns:
        랜덤하게 선택된 User-Agent 문자열
    """
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
    ]
    return random.choice(user_agents)


def get_random_viewport() -> dict:
    """
    랜덤 viewport 크기를 반환한다.
    
    Returns:
        width와 height를 포함한 딕셔너리
    """
    viewports = [
        {"width": 1920, "height": 1080},
        {"width": 1440, "height": 900},
        {"width": 1366, "height": 768},
        {"width": 1536, "height": 864},
        {"width": 1280, "height": 720}
    ]
    return random.choice(viewports)


async def random_delay(min_seconds: float = 2.0, max_seconds: float = 3.0) -> None:
    """
    랜덤한 시간 동안 비동기 대기한다.
    
    Args:
        min_seconds: 최소 대기 시간(초)
        max_seconds: 최대 대기 시간(초)
    """
    delay = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(delay)


def parse_price(price_text: str) -> Optional[int]:
    """
    가격 텍스트를 파싱하여 정수로 변환한다.
    
    Args:
        price_text: 가격 텍스트 (예: "₩29,900", "29,900원")
        
    Returns:
        파싱된 가격 (정수), 실패 시 None
    """
    if not price_text:
        return None
    
    # 숫자가 아닌 문자 제거
    cleaned = ''.join(filter(str.isdigit, price_text))
    
    try:
        return int(cleaned)
    except ValueError:
        return None


def log_error(logger: logging.Logger, branduid: str, reason: str, trace: Optional[str] = None) -> None:
    """
    에러를 JSON 형식으로 로깅한다.
    
    Args:
        logger: 로거 인스턴스
        branduid: 제품 ID
        reason: 에러 원인
        trace: 스택 트레이스 (옵션)
    """
    error_data = {
        "branduid": branduid,
        "reason": reason,
        "trace": trace or "",
        "timestamp": datetime.now().isoformat()
    }
    
    logger.error(json.dumps(error_data, ensure_ascii=False))


def clean_text(text: str) -> str:
    """
    텍스트를 정리한다.
    
    Args:
        text: 정리할 텍스트
        
    Returns:
        정리된 텍스트
    """
    if not text:
        return ""
    
    # 공백 문자 정리
    return " ".join(text.strip().split())


def extract_options_from_text(text: str) -> List[str]:
    """
    텍스트에서 옵션 정보를 추출한다.
    
    Args:
        text: 옵션이 포함된 텍스트
        
    Returns:
        추출된 옵션 목록
    """
    # TODO: 실제 사이트 구조에 맞게 구현 필요
    if not text:
        return []
    
    # 간단한 구분자 기반 파싱 (실제 구현 시 수정 필요)
    options = [opt.strip() for opt in text.split(',') if opt.strip()]
    return options


def convert_country_to_code(country_name: str) -> str:
    """
    국가명을 2글자 국가 코드로 변환한다.
    특수기호(■, ●, ◆ 등)를 제거하고 한글 텍스트만 추출하여 매핑한다.
    복합 국가명과 특수 형태의 국가 표기에 대한 예외처리를 포함한다.
    
    Args:
        country_name: 국가명 (한국어/영어, 특수기호 포함 가능)
        
    Returns:
        2글자 국가 코드 (예: KR, US, CN) 또는 원본 텍스트 (매칭되지 않는 경우)
    """
    if not country_name:
        return ""
    
    import re
    
    # 특수기호 제거 및 한글/영어 텍스트만 추출
    # ■, ●, ◆, ▲, ★, ※ 등 특수기호와 공백을 제거
    cleaned_country = re.sub(r'[^\w\s가-힣a-zA-Z,/]', '', country_name)
    cleaned_country = cleaned_country.strip()
    
    # 복합 국가명 처리 - 첫 번째 국가를 우선으로 반환
    if '/' in cleaned_country or ',' in cleaned_country:
        # 구분자로 분리하여 첫 번째 국가 사용
        separators = ['/', ',']
        for sep in separators:
            if sep in cleaned_country:
                first_country = cleaned_country.split(sep)[0].strip()
                # 재귀 호출로 첫 번째 국가만 처리
                return convert_country_to_code(first_country)
    
    # 특수 형태의 국가 표기 처리
    special_patterns = {
        r'made\s+in\s+korea': 'KR',
        r'국내산': 'KR',
        r'중국\s*oem': 'CN',
        r'제조국\s*:\s*중국': 'CN',
    }
    
    country_lower_for_pattern = cleaned_country.lower()
    for pattern, code in special_patterns.items():
        if re.search(pattern, country_lower_for_pattern):
            return code
    
    # 국가명을 소문자로 변환하여 매칭
    country_lower = cleaned_country.lower().strip()
    
    # 국가명 -> 국가코드 매핑 사전
    country_name_to_code = {
        # 한국
        "한국": "KR",
        "대한민국": "KR",
        "korea": "KR",
        "south korea": "KR",
        "republic of korea": "KR",

        # 일본
        "일본": "JP",
        "japan": "JP",

        # 중국
        "중국": "CN",
        "china": "CN",
        "prc": "CN",

        # 미국
        "미국": "US",
        "usa": "US",
        "united states": "US",
        "united states of america": "US",

        # 베트남
        "베트남": "VN",
        "vietnam": "VN",

        # 대만
        "대만": "TW",
        "taiwan": "TW",

        # 독일
        "독일": "DE",
        "germany": "DE",

        # 프랑스
        "프랑스": "FR",
        "france": "FR",

        # 태국
        "태국": "TH",
        "thailand": "TH",

        # 인도네시아
        "인도네시아": "ID",
        "indonesia": "ID",

        # 필리핀
        "필리핀": "PH",
        "philippines": "PH",

        # 말레이시아
        "말레이시아": "MY",
        "malaysia": "MY",

        # 영국
        "영국": "GB",
        "uk": "GB",
        "united kingdom": "GB",

        # 인도
        "인도": "IN",
        "india": "IN",

        # 캐나다
        "캐나다": "CA",
        "canada": "CA",

        # 호주
        "호주": "AU",
        "australia": "AU",

        # 러시아
        "러시아": "RU",
        "russia": "RU",

        # 벨기에
        "벨기에": "BE",
        "belgium": "BE",

        # 스페인
        "스페인": "ES",
        "spain": "ES",

        # 네덜란드
        "네덜란드": "NL",
        "netherlands": "NL",

        # 노르웨이
        "노르웨이": "NO",
        "norway": "NO",

        # 덴마크
        "덴마크": "DK",
        "denmark": "DK",

        # 영국
        "영국": "GB",
        "uk": "GB",
        "united kingdom": "GB",

        # 이탈리아
        "이탈리아": "IT",
        "italy": "IT",
        
        # 뉴질랜드
        "뉴질랜드": "NZ",
        "new zealand": "NZ",
        
        # 폴란드
        "폴란드": "PL",
        "poland": "PL",
        
        # 체코
        "체코": "CZ",
        "czech": "CZ",
        "czech republic": "CZ",

    }
     
    # 매핑 테이블에서 찾기
    country_code = country_name_to_code.get(country_lower, "")
    
    if country_code:
        return country_code
    else:
        # 매칭되지 않으면 원본 텍스트 반환
        return country_name


def extract_weight_numbers(weight_text: str) -> str:
    """
    중량 텍스트에서 숫자만 추출한다.
    
    Args:
        weight_text: 중량 텍스트 (예: "15g (약 15그램)", "25g", "10.5g (약)", "100g(포장지포함)")
        
    Returns:
        숫자만 추출된 중량 (예: "15", "25", "10.5", "100")
    """
    if not weight_text:
        return ""
    
    import re
    
    # 괄호와 그 안의 내용 제거
    cleaned_text = re.sub(r'\([^)]*\)', '', weight_text)
    
    # 숫자와 소수점만 추출 (g, kg 등 단위 제거)
    numbers = re.findall(r'\d+\.?\d*', cleaned_text)
    
    if numbers:
        # 첫 번째 숫자 반환 (가장 중요한 중량값)
        return numbers[0]
    else:
        return ""
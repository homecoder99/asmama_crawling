"""브랜드 번역 파일 관리 시스템.

브랜드 번역을 CSV 파일로 관리하여 반복적인 API 호출을 방지한다.
"""

import os
import csv
import logging
from typing import Dict, Optional, List, Tuple
from pathlib import Path
from datetime import datetime
import openai
import dotenv

# 환경변수 로드
dotenv.load_dotenv()


class BrandTranslationManager:
    """
    브랜드 번역을 CSV 파일로 관리하는 클래스.
    
    기능:
    - CSV 파일에서 기존 번역 로드
    - 새로운 브랜드 자동 번역 및 파일 추가
    - 번역 결과 검증 및 수동 수정 지원
    """
    
    def __init__(self, translation_file: str = "uploader/templates/translation/brand_translations.csv"):
        """
        BrandTranslationManager 초기화.
        
        Args:
            translation_file: 브랜드 번역 CSV 파일 경로
        """
        self.logger = logging.getLogger(__name__)
        self.translation_file = Path(translation_file)
        
        # 디렉토리 생성
        self.translation_file.parent.mkdir(parents=True, exist_ok=True)
        
        # OpenAI 클라이언트
        self.openai_client = openai.OpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # 번역 데이터 로드
        self.translations = self._load_translations()
        
        # 통계
        self.stats = {
            "file_hits": 0,
            "new_translations": 0,
            "api_calls": 0
        }
        
        self.logger.info(f"브랜드 번역 관리자 초기화 완료 - 기존 번역: {len(self.translations)}개")
    
    def _load_translations(self) -> Dict[str, Dict[str, str]]:
        """
        CSV 파일에서 브랜드 번역 데이터를 로드한다.
        
        Returns:
            {korean_brand: {english_brand, japanese_brand, ...}} 딕셔너리
        """
        translations = {}
        
        try:
            if not self.translation_file.exists():
                self._create_empty_csv()
                return translations
            
            with open(self.translation_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    korean_brand = row.get('korean_brand', '').strip()
                    if korean_brand:
                        translations[korean_brand] = {
                            'english_brand': row.get('english_brand', '').strip(),
                            'japanese_brand': row.get('japanese_brand', '').strip(),
                            'created_date': row.get('created_date', ''),
                            'verified': row.get('verified', 'false').lower() == 'true'
                        }
            
            self.logger.info(f"브랜드 번역 파일 로드 완료: {len(translations)}개")
            return translations
            
        except Exception as e:
            self.logger.error(f"브랜드 번역 파일 로드 실패: {str(e)}")
            return {}
    
    def _create_empty_csv(self):
        """
        빈 CSV 파일을 생성한다.
        """
        try:
            with open(self.translation_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['korean_brand', 'english_brand', 'japanese_brand', 'created_date', 'verified'])
            self.logger.info("빈 브랜드 번역 CSV 파일 생성 완료")
        except Exception as e:
            self.logger.error(f"빈 CSV 파일 생성 실패: {str(e)}")
    
    def get_brand_translation(self, korean_brand: str, target_lang: str = "english") -> Optional[str]:
        """
        브랜드 번역을 가져온다. 없으면 자동으로 번역해서 파일에 추가한다.
        
        Args:
            korean_brand: 한국어 브랜드명
            target_lang: 목표 언어 ("english" 또는 "japanese")
            
        Returns:
            번역된 브랜드명 또는 None
        """
        if not korean_brand or not korean_brand.strip():
            return None
        
        korean_brand = korean_brand.strip()
        
        # 파일에서 기존 번역 확인
        if korean_brand in self.translations:
            translation_data = self.translations[korean_brand]
            target_key = f"{target_lang}_brand"
            
            if target_key in translation_data and translation_data[target_key]:
                self.stats["file_hits"] += 1
                result = translation_data[target_key]
                self.logger.debug(f"브랜드 파일 히트: {korean_brand} → {result}")
                return result
        
        # 새로운 번역 필요
        self.logger.info(f"새로운 브랜드 번역 시작: {korean_brand}")
        english_translation, japanese_translation = self._translate_new_brand(korean_brand)
        
        if english_translation or japanese_translation:
            # 파일에 추가
            self._add_translation_to_file(korean_brand, english_translation, japanese_translation)
            
            # 메모리 캐시 업데이트
            self.translations[korean_brand] = {
                'english_brand': english_translation or '',
                'japanese_brand': japanese_translation or '',
                'created_date': datetime.now().strftime('%Y-%m-%d'),
                'verified': False
            }
            
            self.stats["new_translations"] += 1
            
            # 요청된 언어 반환
            if target_lang == "english":
                return english_translation
            else:
                return japanese_translation
        
        return None
    
    def _translate_new_brand(self, korean_brand: str) -> Tuple[Optional[str], Optional[str]]:
        """
        새로운 브랜드를 영어와 일본어로 동시에 번역한다.
        간단한 구분자 형식 사용: "English|Japanese"
        
        Args:
            korean_brand: 번역할 한국어 브랜드명
            
        Returns:
            (영어_번역, 일본어_번역) 튜플
        """
        try:
            self.stats["api_calls"] += 1
            response = self.openai_client.responses.create(
                model="gpt-5-mini",
                input=f"""Translate the Korean brand name to English and Japanese.
For English: Use official English brand names if known, otherwise romanize appropriately.  
For Japanese: Use katakana for foreign brands, appropriate Japanese for Korean brands.

Respond in this exact format: English_name|Japanese_name
Example: The Face Shop|ザ・フェイスショップ

Korean brand name: "{korean_brand}\""""
            )
            
            result_text = response.output_text.strip()
            
            # 파싱 (구분자 기반)
            if '|' in result_text:
                parts = result_text.split('|', 1)
                english = parts[0].strip() if len(parts) > 0 else ""
                japanese = parts[1].strip() if len(parts) > 1 else ""
            else:
                # 구분자가 없는 경우 전체를 영어로 간주
                english = result_text
                japanese = ""
            
            self.logger.info(f"브랜드 번역 완료: '{korean_brand}' → EN: '{english}', JP: '{japanese}'")
            return english, japanese
            
        except Exception as e:
            self.logger.error(f"브랜드 번역 실패: {korean_brand} - {str(e)}")
            return None, None
    
    def _add_translation_to_file(self, korean_brand: str, english_brand: str, japanese_brand: str):
        """
        새로운 번역을 CSV 파일에 추가한다.
        
        Args:
            korean_brand: 한국어 브랜드명
            english_brand: 영어 번역
            japanese_brand: 일본어 번역
        """
        try:
            # 파일이 존재하고 줄바꿈으로 끝나지 않는 경우 줄바꿈 추가
            if self.translation_file.exists():
                with open(self.translation_file, 'r', encoding='utf-8-sig') as f:
                    content = f.read()
                    if content and not content.endswith('\n'):
                        with open(self.translation_file, 'a', encoding='utf-8-sig') as append_f:
                            append_f.write('\n')
            
            with open(self.translation_file, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    korean_brand,
                    english_brand or '',
                    japanese_brand or '',
                    datetime.now().strftime('%Y-%m-%d'),
                    'false'  # 자동 번역이므로 미검증
                ])
            
            self.logger.info(f"브랜드 번역 파일 추가: {korean_brand}")
            
        except Exception as e:
            self.logger.error(f"브랜드 번역 파일 추가 실패: {str(e)}")
    
    def get_stats(self) -> Dict[str, any]:
        """
        통계 정보를 반환한다.
        
        Returns:
            통계 딕셔너리
        """
        total_requests = self.stats["file_hits"] + self.stats["new_translations"]
        file_hit_rate = (self.stats["file_hits"] / total_requests * 100) if total_requests > 0 else 0
        
        verified_count = sum(1 for data in self.translations.values() if data.get('verified', False))
        
        return {
            "total_brands": len(self.translations),
            "verified_brands": verified_count,
            "unverified_brands": len(self.translations) - verified_count,
            "total_requests": total_requests,
            "file_hits": self.stats["file_hits"],
            "new_translations": self.stats["new_translations"],
            "file_hit_rate": file_hit_rate,
            "api_calls": self.stats["api_calls"]
        }
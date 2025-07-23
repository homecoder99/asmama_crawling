"""유틸리티 함수 테스트."""

import pytest
import logging
from unittest.mock import patch, MagicMock

from crawler.utils import (
    get_random_user_agent,
    get_random_viewport,
    parse_price,
    clean_text,
    extract_options_from_text,
    log_error
)


class TestUtils:
    """유틸리티 함수들의 단위 테스트."""
    
    def test_get_random_user_agent(self):
        """랜덤 User-Agent 생성 테스트."""
        user_agent = get_random_user_agent()
        
        assert isinstance(user_agent, str)
        assert len(user_agent) > 0
        assert "Mozilla" in user_agent
    
    def test_get_random_viewport(self):
        """랜덤 viewport 생성 테스트."""
        viewport = get_random_viewport()
        
        assert isinstance(viewport, dict)
        assert "width" in viewport
        assert "height" in viewport
        assert isinstance(viewport["width"], int)
        assert isinstance(viewport["height"], int)
        assert viewport["width"] > 0
        assert viewport["height"] > 0
    
    @pytest.mark.parametrize("price_text,expected", [
        ("₩29,900", 29900),
        ("29,900원", 29900),
        ("$19.99", 1999),
        ("1,234,567", 1234567),
        ("무료", None),
        ("", None),
        (None, None),
        ("abc", None),
    ])
    def test_parse_price(self, price_text, expected):
        """가격 파싱 테스트."""
        result = parse_price(price_text)
        assert result == expected
    
    @pytest.mark.parametrize("text,expected", [
        ("  hello   world  ", "hello world"),
        ("", ""),
        (None, ""),
        ("single", "single"),
        ("  \n\t  multiple\n\nlines  \t  ", "multiple lines"),
    ])
    def test_clean_text(self, text, expected):
        """텍스트 정리 테스트."""
        result = clean_text(text)
        assert result == expected
    
    @pytest.mark.parametrize("text,expected", [
        ("red, blue, green", ["red", "blue", "green"]),
        ("single", ["single"]),
        ("", []),
        (None, []),
        ("option1,option2,option3", ["option1", "option2", "option3"]),
        ("  spaced  ,  options  ", ["spaced", "options"]),
    ])
    def test_extract_options_from_text(self, text, expected):
        """옵션 추출 테스트."""
        result = extract_options_from_text(text)
        assert result == expected
    
    @patch('json.dumps')
    def test_log_error(self, mock_json_dumps):
        """에러 로깅 테스트."""
        # Mock 설정
        mock_logger = MagicMock()
        mock_json_dumps.return_value = '{"test": "data"}'
        
        # 함수 실행
        log_error(mock_logger, "test123", "Test error", "Stack trace")
        
        # 검증
        mock_logger.error.assert_called_once()
        mock_json_dumps.assert_called_once()
        
        # JSON 데이터 검증
        call_args = mock_json_dumps.call_args[0][0]
        assert call_args["branduid"] == "test123"
        assert call_args["reason"] == "Test error"
        assert call_args["trace"] == "Stack trace"
        assert "timestamp" in call_args
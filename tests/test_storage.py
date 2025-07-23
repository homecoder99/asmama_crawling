"""저장소 클래스 테스트."""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from crawler.storage import ExcelStorage, JSONStorage


class TestJSONStorage:
    """JSON 저장소 테스트."""
    
    def test_init(self):
        """초기화 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test.json"
            storage = JSONStorage(str(file_path))
            
            assert storage.file_path == file_path
            assert file_path.parent.exists()
    
    def test_save_and_load_single_item(self):
        """단일 아이템 저장 및 로드 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test.json"
            storage = JSONStorage(str(file_path))
            
            test_data = {
                "branduid": "test123",
                "name": "Test Product",
                "price": 29900
            }
            
            # 저장 테스트
            result = storage.save(test_data)
            assert result is True
            assert file_path.exists()
            
            # 로드 테스트
            loaded_data = storage.load()
            assert len(loaded_data) == 1
            assert loaded_data[0] == test_data
    
    def test_save_and_load_multiple_items(self):
        """다중 아이템 저장 및 로드 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test.json"
            storage = JSONStorage(str(file_path))
            
            test_data = [
                {"branduid": "test1", "name": "Product 1"},
                {"branduid": "test2", "name": "Product 2"}
            ]
            
            # 저장 테스트
            result = storage.save(test_data)
            assert result is True
            
            # 로드 테스트
            loaded_data = storage.load()
            assert len(loaded_data) == 2
            assert loaded_data == test_data
    
    def test_clear(self):
        """데이터 삭제 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test.json"
            storage = JSONStorage(str(file_path))
            
            # 데이터 저장
            storage.save({"test": "data"})
            assert file_path.exists()
            
            # 삭제 테스트
            result = storage.clear()
            assert result is True
            assert not file_path.exists()
    
    def test_load_empty_file(self):
        """빈 파일 로드 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "nonexistent.json"
            storage = JSONStorage(str(file_path))
            
            loaded_data = storage.load()
            assert loaded_data == []


class TestExcelStorage:
    """Excel 저장소 테스트."""
    
    @patch('crawler.storage.PANDAS_AVAILABLE', True)
    @patch('crawler.storage.OPENPYXL_AVAILABLE', True)
    @patch('crawler.storage.pd')
    def test_init_with_dependencies(self, mock_pd):
        """의존성 있을 때 초기화 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test.xlsx"
            
            # Mock DataFrame
            mock_df = MagicMock()
            mock_df.to_dict.return_value = []
            mock_pd.read_excel.return_value = mock_df
            
            storage = ExcelStorage(str(file_path))
            assert storage.file_path == file_path
    
    @patch('crawler.storage.PANDAS_AVAILABLE', False)
    def test_init_without_pandas(self):
        """pandas 없을 때 초기화 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test.xlsx"
            
            with pytest.raises(ImportError, match="pandas가 설치되지 않았습니다"):
                ExcelStorage(str(file_path))
    
    @patch('crawler.storage.PANDAS_AVAILABLE', True)
    @patch('crawler.storage.OPENPYXL_AVAILABLE', False)
    def test_init_without_openpyxl(self):
        """openpyxl 없을 때 초기화 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test.xlsx"
            
            with pytest.raises(ImportError, match="openpyxl이 설치되지 않았습니다"):
                ExcelStorage(str(file_path))
    
    @patch('crawler.storage.PANDAS_AVAILABLE', True)
    @patch('crawler.storage.OPENPYXL_AVAILABLE', True)
    @patch('crawler.storage.pd')
    def test_save_success(self, mock_pd):
        """저장 성공 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test.xlsx"
            
            # Mock 설정
            mock_df = MagicMock()
            mock_df.to_dict.return_value = []
            mock_df.columns = ['branduid', 'name', 'price']
            mock_df.__getitem__ = MagicMock()
            mock_pd.read_excel.return_value = mock_df
            mock_pd.DataFrame.return_value = mock_df
            
            storage = ExcelStorage(str(file_path))
            
            test_data = {"branduid": "test123", "name": "Test Product"}
            result = storage.save(test_data)
            
            assert result is True
            mock_df.to_excel.assert_called_once()
    
    @patch('crawler.storage.PANDAS_AVAILABLE', True)
    @patch('crawler.storage.OPENPYXL_AVAILABLE', True)
    @patch('crawler.storage.pd')
    def test_get_stats(self, mock_pd):
        """통계 정보 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test.xlsx"
            
            # Mock 설정
            mock_df = MagicMock()
            mock_df.to_dict.return_value = []
            mock_df.columns = ['branduid', 'name', 'price']
            mock_df.__len__ = MagicMock(return_value=5)
            mock_pd.read_excel.return_value = mock_df
            mock_pd.DataFrame.return_value = mock_df
            
            storage = ExcelStorage(str(file_path))
            
            # 파일이 없는 경우
            stats = storage.get_stats()
            assert "total_count" in stats
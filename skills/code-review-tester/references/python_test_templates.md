# Python 测试模板

## 1. 基础单元测试模板

### 1.1 简单函数测试
```python
"""
测试模块说明
"""

import pytest
from typing import Any

from path.to.module import function_name


class TestFunctionName:
    """测试 function_name 函数"""

    def test_normal_input(self):
        """测试正常输入"""
        # Arrange
        input_data = "test"
        expected = "expected_result"
        
        # Act
        result = function_name(input_data)
        
        # Assert
        assert result == expected

    def test_empty_input(self):
        """测试空输入"""
        # Arrange
        input_data = ""
        
        # Act
        result = function_name(input_data)
        
        # Assert
        assert result is not None

    def test_none_input(self):
        """测试 None 输入"""
        # Arrange
        input_data = None
        
        # Act & Assert
        with pytest.raises(ValueError):
            function_name(input_data)
```

### 1.2 类测试模板
```python
"""
测试类说明
"""

import pytest
from path.to.module import ClassName


class TestClassName:
    """测试 ClassName 类"""

    @pytest.fixture
    def instance(self):
        """创建测试实例"""
        return ClassName(config="test_config")

    def test_initialization(self, instance):
        """测试初始化"""
        assert instance is not None
        assert instance.config == "test_config"

    def test_method_one(self, instance):
        """测试 method_one 方法"""
        # Arrange
        param = "value"
        
        # Act
        result = instance.method_one(param)
        
        # Assert
        assert result == "expected"

    def test_method_two_with_error(self, instance):
        """测试 method_two 异常情况"""
        # Arrange
        invalid_param = -1
        
        # Act & Assert
        with pytest.raises(ValueError, match="参数必须为正数"):
            instance.method_two(invalid_param)
```

## 2. 使用项目 Fixture 的测试模板

### 2.1 使用 config_paths fixture
```python
"""
使用配置隔离的测试
"""

import pytest
from pathlib import Path
from typing import Dict

from manju_web.backend.repositories import config_repo


class TestConfigRepo:
    """测试配置仓库"""

    def test_save_and_load_config(self, config_paths: Dict[str, Path]):
        """测试保存和加载配置"""
        # Arrange
        test_config = {"key": "value"}
        
        # Act
        config_repo.save_global_config(test_config)
        loaded_config = config_repo.load_global_config()
        
        # Assert
        assert loaded_config == test_config
        assert config_paths["global"].exists()
```

### 2.2 使用 isolate_output_dir fixture
```python
"""
使用输出目录隔离的测试
"""

import pytest
from pathlib import Path

from manju_web.backend.repositories import project_repo


class TestProjectRepo:
    """测试项目仓库"""

    def test_create_project(self, isolate_output_dir: Path):
        """测试创建项目"""
        # Arrange
        project_id = "test_project"
        
        # Act
        project = project_repo.create_project(project_id, "Test Project")
        
        # Assert
        assert project.project_id == project_id
        assert (isolate_output_dir / project_id).exists()
```

## 3. 集成测试模板

### 3.1 服务集成测试
```python
"""
服务集成测试
"""

import pytest
from pathlib import Path
from typing import Dict

from manju_web.backend.services import job_service, project_service


class TestJobAndProjectIntegration:
    """测试 Job 和 Project 服务集成"""

    def test_create_job_for_project(
        self,
        config_paths: Dict[str, Path],
        isolate_output_dir: Path
    ):
        """测试为项目创建 Job"""
        # Arrange
        project_id = "test_project"
        project_service.create_project(project_id, "Test Project")
        
        # Act
        job = job_service.create_job(project_id, "test_job", {})
        
        # Assert
        assert job.job_id == "test_job"
        assert job.project_id == project_id
        assert job.status == "pending"
```

### 3.2 文件操作集成测试
```python
"""
文件操作集成测试
"""

import pytest
from pathlib import Path
import json

from manju_web.backend.repositories import asset_repo


class TestAssetRepoIntegration:
    """测试资产仓库集成"""

    def test_save_and_load_asset(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """测试保存和加载资产"""
        # Arrange
        asset_dir = tmp_path / "assets"
        asset_dir.mkdir()
        monkeypatch.setattr(asset_repo, "ASSET_DIR", asset_dir)
        
        asset_data = {
            "asset_id": "test_asset",
            "type": "image",
            "path": "/path/to/image.png"
        }
        
        # Act
        asset_repo.save_asset(asset_data)
        loaded_asset = asset_repo.load_asset("test_asset")
        
        # Assert
        assert loaded_asset == asset_data
        assert (asset_dir / "test_asset.json").exists()
```

## 4. Mock 测试模板

### 4.1 使用 monkeypatch Mock
```python
"""
使用 monkeypatch 的测试
"""

import pytest
from unittest.mock import Mock

from path.to.module import Service


class TestServiceWithMock:
    """测试使用 mock 的服务"""

    def test_with_monkeypatch(self, monkeypatch: pytest.MonkeyPatch):
        """使用 monkeypatch mock 外部依赖"""
        # Arrange
        mock_result = {"status": "success"}
        
        def mock_external_call(*args, **kwargs):
            return mock_result
        
        monkeypatch.setattr("path.to.module.external_api", mock_external_call)
        
        service = Service()
        
        # Act
        result = service.process()
        
        # Assert
        assert result == mock_result

    def test_with_mock_object(self):
        """使用 mock 对象"""
        # Arrange
        mock_dependency = Mock()
        mock_dependency.method.return_value = "mocked"
        
        service = Service(dependency=mock_dependency)
        
        # Act
        result = service.do_something()
        
        # Assert
        assert result == "mocked"
        mock_dependency.method.assert_called_once()
```

### 4.2 使用 patch 装饰器
```python
"""
使用 patch 的测试
"""

import pytest
from unittest.mock import patch, Mock

from path.to.module import function_that_calls_api


class TestWithPatch:
    """使用 patch 装饰器的测试"""

    @patch("path.to.module.requests.get")
    def test_api_call(self, mock_get: Mock):
        """测试 API 调用"""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_get.return_value = mock_response
        
        # Act
        result = function_that_calls_api("https://api.example.com")
        
        # Assert
        mock_get.assert_called_once_with("https://api.example.com")
        assert result == {"data": "test"}

    @patch("path.to.module.external_function")
    def test_with_multiple_mocks(
        self,
        mock_external: Mock,
        monkeypatch: pytest.MonkeyPatch
    ):
        """使用多个 mock"""
        # Arrange
        mock_external.return_value = "external"
        monkeypatch.setenv("TEST_ENV", "true")
        
        # Act
        result = function_that_uses_both()
        
        # Assert
        assert result == "external"
```

## 5. 参数化测试模板

### 5.1 使用 @pytest.mark.parametrize
```python
"""
参数化测试
"""

import pytest

from path.to.module import calculate


class TestParameterized:
    """参数化测试"""

    @pytest.mark.parametrize("input_a, input_b, expected", [
        (1, 2, 3),
        (0, 0, 0),
        (-1, 1, 0),
        (100, 200, 300),
    ])
    def test_addition(self, input_a: int, input_b: int, expected: int):
        """测试加法（参数化）"""
        # Act
        result = calculate.add(input_a, input_b)
        
        # Assert
        assert result == expected

    @pytest.mark.parametrize("invalid_input, expected_error", [
        (None, TypeError),
        ("string", TypeError),
        ([], TypeError),
    ])
    def test_invalid_inputs(self, invalid_input: Any, expected_error: type):
        """测试无效输入（参数化）"""
        # Act & Assert
        with pytest.raises(expected_error):
            calculate.process(invalid_input)
```

## 6. 测试数据工厂模板

### 6.1 测试数据工厂函数
```python
"""
测试数据工厂
"""

from typing import Dict, Any
from datetime import datetime


def create_test_job(
    job_id: str = "test_job",
    project_id: str = "test_project",
    status: str = "pending",
    **kwargs: Any
) -> Dict[str, Any]:
    """
    创建测试 Job 数据
    
    Args:
        job_id: Job ID
        project_id: 项目 ID
        status: 状态
        **kwargs: 其他参数
    
    Returns:
        Job 数据字典
    """
    base = {
        "job_id": job_id,
        "project_id": project_id,
        "status": status,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "metadata": {},
    }
    base.update(kwargs)
    return base


def create_test_project(
    project_id: str = "test_project",
    name: str = "Test Project",
    **kwargs: Any
) -> Dict[str, Any]:
    """创建测试 Project 数据"""
    base = {
        "project_id": project_id,
        "name": name,
        "created_at": datetime.now().isoformat(),
        "config": {},
    }
    base.update(kwargs)
    return base
```

## 7. 完整测试文件示例

### 7.1 完整的测试文件
```python
"""
测试示例模块
"""

import pytest
from pathlib import Path
from typing import Dict, Any

from manju_web.backend.services.example_service import ExampleService
from manju_web.backend.repositories.example_repo import ExampleRepo


class TestExampleService:
    """测试 ExampleService"""

    @pytest.fixture
    def service(self, config_paths: Dict[str, Path]):
        """创建服务实例"""
        return ExampleService()

    def test_create_item(self, service: ExampleService, isolate_output_dir: Path):
        """测试创建项目"""
        # Arrange
        item_data = {"name": "Test Item", "value": 123}
        
        # Act
        item = service.create_item(item_data)
        
        # Assert
        assert item.name == "Test Item"
        assert item.value == 123
        assert item.id is not None

    @pytest.mark.parametrize("invalid_data, expected_error", [
        ({}, ValueError),
        ({"name": ""}, ValueError),
        ({"value": -1}, ValueError),
    ])
    def test_create_item_invalid_data(
        self,
        service: ExampleService,
        invalid_data: Dict[str, Any],
        expected_error: type
    ):
        """测试创建项目时的无效数据"""
        # Act & Assert
        with pytest.raises(expected_error):
            service.create_item(invalid_data)

    def test_get_item_not_found(self, service: ExampleService):
        """测试获取不存在的项目"""
        # Act & Assert
        with pytest.raises(FileNotFoundError):
            service.get_item("non_existent_id")
```

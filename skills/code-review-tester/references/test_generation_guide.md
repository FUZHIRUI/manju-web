# 测试生成指南

## 1. 测试策略

### 1.1 测试金字塔
- **单元测试**：测试单个函数/类，快速、独立、大量
- **集成测试**：测试模块间的交互，适中数量
- **端到端测试**：测试完整业务流程，少量

### 1.2 测试原则
- **FIRST**：Fast（快速）、Independent（独立）、Repeatable（可重复）、Self-validating（自验证）、Timely（及时）
- **AAA**：Arrange（准备）、Act（执行）、Assert（断言）
- **Given-When-Then**：Given（给定条件）、When（当执行操作）、Then（那么结果）

## 2. 单元测试生成

### 2.1 分析目标代码
1. 理解函数的功能和职责
2. 识别输入参数和输出结果
3. 分析函数的逻辑分支
4. 识别边界条件和异常情况

### 2.2 设计测试用例
#### 正常情况测试
- 典型输入值
- 不同的有效输入组合
- 正常的业务流程

#### 边界条件测试
- 最小值/最大值
- 空值/空列表/空字典
- 边界值附近的值
- 零值/负数

#### 异常情况测试
- 无效输入
- 错误的数据类型
- 网络错误
- 文件不存在

### 2.3 测试文件结构
```python
"""
测试模块文档字符串
"""

import pytest
from pathlib import Path
from typing import Any

from module import function_to_test


class TestFunctionName:
    """测试类文档字符串"""

    def test_normal_case(self):
        """测试正常情况"""
        # Arrange
        input_data = ...
        expected = ...
        
        # Act
        result = function_to_test(input_data)
        
        # Assert
        assert result == expected

    def test_boundary_case(self):
        """测试边界条件"""
        # Arrange
        input_data = ...
        
        # Act
        result = function_to_test(input_data)
        
        # Assert
        ...

    def test_error_case(self):
        """测试异常情况"""
        # Arrange
        invalid_input = ...
        
        # Act & Assert
        with pytest.raises(ExpectedError):
            function_to_test(invalid_input)
```

## 3. 集成测试生成

### 3.1 确定集成点
1. 识别模块之间的依赖关系
2. 确定API端点和调用链
3. 分析数据流和状态变化
4. 识别外部依赖（数据库、文件系统等）

### 3.2 测试环境隔离
- 使用临时目录（tmp_path fixture）
- 使用 monkeypatch 修改环境变量
- Mock 外部服务调用
- 使用测试数据库

### 3.3 集成测试示例
```python
"""
集成测试模块
"""

import pytest
from pathlib import Path

from module_a import ServiceA
from module_b import ServiceB


class TestIntegration:
    """集成测试"""

    def test_service_chain(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """测试服务链集成"""
        # Arrange - 设置测试环境
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        monkeypatch.setenv("OUTPUT_DIR", str(output_dir))
        
        service_a = ServiceA()
        service_b = ServiceB()
        
        # Act - 执行业务流程
        data = service_a.process("input")
        result = service_b.handle(data)
        
        # Assert - 验证结果
        assert result is not None
        assert (output_dir / "result.json").exists()
```

## 4. 参考项目现有测试

### 4.1 conftest.py 中的 fixture
项目 `backend/tests/conftest.py` 提供了以下 fixture：
- `config_paths` - 隔离配置文件
- `isolate_output_dir` - 隔离输出目录
- `project_output_dir` - 项目输出目录
- `job_repo_state` - Job仓库状态

### 4.2 测试文件命名
- 单元测试：`test_<模块名>.py`
- 集成测试：`test_<模块名>_integration.py`

### 4.3 运行测试命令
```bash
# 运行所有测试
pytest backend/tests/

# 运行特定测试文件
pytest backend/tests/test_module.py

# 运行特定测试类
pytest backend/tests/test_module.py::TestClass

# 运行特定测试方法
pytest backend/tests/test_module.py::TestClass::test_method

# 显示详细输出
pytest -v

# 显示打印输出
pytest -s

# 生成覆盖率报告
pytest --cov=backend --cov-report=html
```

## 5. Mock 技巧

### 5.1 使用 monkeypatch
```python
def test_with_monkeypatch(monkeypatch: pytest.MonkeyPatch):
    """使用 monkeypatch 修改环境变量和属性"""
    # 修改环境变量
    monkeypatch.setenv("API_KEY", "test_key")
    
    # 修改模块属性
    monkeypatch.setattr(module, "CONFIG_PATH", "/tmp/test_config.json")
    
    # Mock 函数
    def mock_function():
        return "mocked"
    monkeypatch.setattr(module, "function", mock_function)
```

### 5.2 使用 unittest.mock
```python
from unittest.mock import Mock, patch, MagicMock

def test_with_mock():
    """使用 mock 对象"""
    # 创建 mock 对象
    mock_service = Mock()
    mock_service.method.return_value = "result"
    
    # 使用 mock
    result = mock_service.method("input")
    assert result == "result"
    mock_service.method.assert_called_once_with("input")


@patch("module.external_api")
def test_with_patch(mock_api: Mock):
    """使用 patch 装饰器"""
    mock_api.return_value = {"status": "ok"}
    
    result = function_that_calls_api()
    
    mock_api.assert_called_once()
    assert result == {"status": "ok"}
```

## 6. 测试数据准备

### 6.1 使用 tmp_path
```python
def test_file_operations(tmp_path: Path):
    """测试文件操作"""
    # 创建测试文件
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")
    
    # 创建测试目录
    test_dir = tmp_path / "data"
    test_dir.mkdir()
    
    # 测试代码
    result = process_file(test_file)
    assert result == "test content"
```

### 6.2 测试数据工厂
```python
def create_test_job(job_id: str = "test_job", status: str = "pending") -> dict:
    """创建测试 Job 数据"""
    return {
        "job_id": job_id,
        "status": status,
        "created_at": "2024-01-01T00:00:00Z",
        "metadata": {}
    }
```

## 7. 最佳实践

### 7.1 测试命名
- 测试函数名描述测试的行为：`test_<场景>_<期望结果>`
- 示例：`test_empty_input_returns_default`, `test_invalid_id_raises_error`

### 7.2 测试文档
- 每个测试函数有 docstring 说明测试目的
- 使用 `"""测试..."""` 格式

### 7.3 断言
- 使用具体的断言，避免过于宽泛
- 一个测试只断言一个主要结果
- 使用 pytest 提供的断言增强功能

### 7.4 测试独立性
- 测试之间不共享状态
- 每个测试自己准备数据
- 使用 fixture 共享 setup/teardown 逻辑

### 7.5 测试速度
- 单元测试快速执行（< 1ms）
- 避免不必要的 I/O 操作
- Mock 外部依赖

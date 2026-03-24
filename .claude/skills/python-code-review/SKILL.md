# Python 代码审查技能

> 专业的 Python 代码质量分析工具，专注于发现代码异味、提升代码质量和可维护性。

---

## 技能能力

### 1. 超长函数检测
- 识别行数超过阈值的函数和方法
- 分析函数复杂度（圈复杂度）
- 检测职责过多的"上帝函数"
- 提供拆分建议和重构方案

### 2. 冗余与重复代码检测
- 发现完全相同的代码块
- 识别相似度高的代码片段
- 检测可以提取为公共方法的重复逻辑
- 标记未使用的变量、导入和参数

### 3. 空代码与无效方法检测
- 发现空的函数和方法体
- 识别只有 pass 的抽象方法实现
- 检测未完成的 TODO 代码块
- 标记永远不会执行的死代码

### 4. 内聚性与组件分析
- 分析类的职责内聚性
- 评估模块之间的耦合度
- 识别可以提取的工具方法
- 建议更好的代码组织结构

### 5. 工具型方法识别
- 发现纯函数和工具方法
- 识别可以泛化的重复逻辑
- 建议提取到公共工具模块
- 分析函数的输入输出模式

---

## 使用方法

### 分析整个项目

```bash
# 分析整个代码库
python -m code_review analyze ./src --output report.json

# 生成详细报告
python -m code_review analyze ./src --verbose --output detailed_report.md
```

### 分析单个文件

```bash
# 分析单个 Python 文件
python -m code_review analyze-file ./src/my_module.py

# 只显示特定类型的代码异味
python -m code_review analyze-file ./src/my_module.py --issues long-functions,duplicates
```

### 配置阈值

```yaml
# .code_review.yml 配置文件
thresholds:
  max_function_lines: 50       # 函数最大行数
  max_class_lines: 300         # 类最大行数
  max_parameters: 5              # 最大参数数量
  max_complexity: 10             # 最大圈复杂度
  min_similarity: 0.8            # 重复代码相似度阈值

rules:
  check_empty_functions: true    # 检查空函数
  check_unused_imports: true     # 检查未使用的导入
  check_todo_comments: true      # 检查 TODO 注释
  check_docstrings: true           # 检查文档字符串
```

---

## 审查示例

### 示例 1: 超长函数检测

```python
# 被审查的代码
def process_user_data(data):
    # 这是一个 150 行的函数...
    users = []
    for item in data:
        # ... 很多行代码
        user = {
            'name': item['name'],
            'email': item['email'],
            # ... 更多字段
        }
        users.append(user)
    return users
```

```markdown
# 审查报告

## 问题: 函数过长
- **文件**: `user_service.py:15`
- **函数**: `process_user_data`
- **行数**: 150 行 (阈值: 50 行)

### 问题分析
1. 函数承担了过多的职责：数据验证、转换、过滤、格式化
2. 高圈复杂度 (25)，难以测试和维护
3. 违反了单一职责原则 (SRP)

### 重构建议
```python
def process_user_data(data):
    """主函数：协调各个子步骤"""
    validated_data = _validate_user_data(data)
    users = [_transform_to_user(item) for item in validated_data]
    return _filter_active_users(users)

def _validate_user_data(data):
    """验证用户数据"""
    return [item for item in data if _is_valid_user(item)]

def _transform_to_user(item):
    """将原始数据转换为用户对象"""
    return User(
        name=item['name'],
        email=item['email'],
        # ...
    )

def _filter_active_users(users):
    """过滤活跃用户"""
    return [user for user in users if user.is_active]
```
```

### 示例 2: 重复代码检测

```python
# 被审查的代码 - utils.py
def format_user_name(user):
    if user.get('last_name') and user.get('first_name'):
        return f"{user['last_name']}, {user['first_name']}"
    return user.get('display_name', 'Unknown')

# user_service.py
def format_display_name(user):
    if user.get('last_name') and user.get('first_name'):
        return f"{user['last_name']}, {user['first_name']}"
    return user.get('display_name', 'Unknown')
```

```markdown
## 问题: 重复代码
- **相似度**: 95%
- **位置**:
  - `utils.py:15` - `format_user_name`
  - `user_service.py:42` - `format_display_name`

### 影响
- 维护困难：修改逻辑需要改多个地方
- 代码膨胀：增加不必要的代码量
- 容易遗漏：可能只改了一个地方

### 解决方案
```python
# common/formatters.py
from typing import Dict, Any

def format_user_display_name(user: Dict[str, Any],
                              default: str = 'Unknown') -> str:
    """格式化用户显示名称

    Args:
        user: 用户数据字典
        default: 默认显示名称

    Returns:
        格式化后的显示名称
    """
    if user.get('last_name') and user.get('first_name'):
        return f"{user['last_name']}, {user['first_name']}"
    return user.get('display_name', default)

# 在 utils.py 和 user_service.py 中使用
from common.formatters import format_user_display_name

# utils.py
format_user_display_name(user)

# user_service.py
format_user_display_name(user, default='Guest')
```
```

---

## 输出格式

审查结果支持多种输出格式：

### Markdown 报告
```markdown
# 代码审查报告

## 概览
- **审查文件数**: 25
- **发现问题数**: 12
- **高危问题**: 2
- **建议重构**: 5

## 详细问题列表
...
```

### JSON 报告
```json
{
  "summary": {
    "files_analyzed": 25,
    "issues_found": 12,
    "high_severity": 2
  },
  "issues": [
    {
      "type": "long_function",
      "file": "user_service.py",
      "line": 15,
      "severity": "high",
      "message": "Function exceeds 50 lines"
    }
  ]
}
```

### IDE 集成
支持 VS Code、PyCharm 等主流 IDE 的插件集成，实时显示代码质量问题。

---

## 最佳实践

### 1. 定期审查
- 每次代码提交前进行快速扫描
- 每周进行一次全面审查
- 重大版本发布前进行全面审计

### 2. 团队协作
- 将代码质量指标纳入 CI/CD 流程
- 设置质量门禁（如：不允许新增高危问题）
- 定期分享审查发现和重构案例

### 3. 持续改进
- 根据团队反馈调整审查规则
- 定期更新阈值配置
- 记录和分享重构最佳实践

---

## 相关资源

- [PEP 8 - Python 代码风格指南](https://pep8.org/)
- [Google Python 风格指南](https://google.github.io/styleguide/pyguide.html)
- [重构：改善既有代码的设计](https://book.douban.com/subject/4262627/)
- [代码整洁之道](https://book.douban.com/subject/4199741/)

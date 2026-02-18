"""
io_jsonl.py - JSONL文件读写工具模块

【模块职责】
提供JSON Lines格式文件的读写功能，是整个工作流的数据持久化基础

【JSONL格式说明】
JSON Lines是一种每行一个独立JSON对象的文本格式，便于流式处理和追加写入
- 每行是一个完整的JSON对象
- 行与行之间用换行符分隔
- 不支持跨行的JSON对象

【使用场景】
- 角色列表、地点列表、分镜剧本等结构化数据的存储
- 支持增量写入和流式读取
- 便于与其他工具(如命令行)集成

【示例】
```python
from backend.services.workflow_runtime.io_jsonl import write_jsonl, read_jsonl

# 写入数据
items = [{"id": 1, "name": "角色A"}, {"id": 2, "name": "角色B"}]
write_jsonl("characters.jsonl", items)

# 读取数据
items = read_jsonl("characters.jsonl")
```
"""

import json
from typing import Any, Dict, Iterable, List


def write_jsonl(path: str, items: Iterable[Dict[str, Any]]) -> None:
    """
    将数据写入JSONL文件
    
    【参数】
    - path: 文件路径
    - items: 可迭代的字典列表
    
    【示例】
    >>> write_jsonl("data.jsonl", [{"id": 1}, {"id": 2}])
    """
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    """
    从JSONL文件读取数据
    
    【参数】
    - path: 文件路径
    
    【返回值】
    字典列表，每个字典对应文件中的一行
    
    【异常处理】
    - 跳过空行
    - 解析失败的行会被跳过(静默处理)
    
    【示例】
    >>> items = read_jsonl("data.jsonl")
    >>> print(items)
    [{"id": 1}, {"id": 2}]
    """
    items: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items

#!/usr/bin/env python3
"""
修复visual_audio_assets.py中的project_name线程安全问题
将所有 project_name or runtime_config.PROJECT_NAME 改为安全的处理方式
"""

import re

file_path = "/Users/bytedance/Desktop/常见python/manju_web/backend/services/workflow_runtime/visual_audio_assets.py"

with open(file_path, 'r') as f:
    content = f.read()

# 1. 修复 emit_event 中的 project 参数
# 将 project=project_name or runtime_config.PROJECT_NAME 改为 project=project_name
content = re.sub(
    r'project=project_name or runtime_config\.PROJECT_NAME',
    'project=project_name',
    content
)

# 2. 修复 get_project_prefixes 调用
# 将 runtime_config.get_project_prefixes(project_name or runtime_config.PROJECT_NAME)
# 改为 runtime_config.get_project_prefixes(project_name) if project_name else []
content = re.sub(
    r'runtime_config\.get_project_prefixes\(project_name or runtime_config\.PROJECT_NAME\)',
    'runtime_config.get_project_prefixes(project_name) if project_name else []',
    content
)

with open(file_path, 'w') as f:
    f.write(content)

print("✓ 修复完成")
print("已修复所有 project_name or runtime_config.PROJECT_NAME 的模式")

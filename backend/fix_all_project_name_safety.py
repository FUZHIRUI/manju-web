#!/usr/bin/env python3
"""
修复所有workflow文件中的project_name线程安全问题
将所有 project_name or runtime_config.PROJECT_NAME 改为安全的处理方式
"""

import re
import os

files_to_fix = [
    "/Users/bytedance/Desktop/常见python/manju_web/backend/services/workflow_runtime/auto_storyboard.py",
    "/Users/bytedance/Desktop/常见python/manju_web/backend/services/workflow_runtime/provider_runtime.py",
    "/Users/bytedance/Desktop/常见python/manju_web/backend/services/workflow_runtime/fenjing.py",
    "/Users/bytedance/Desktop/常见python/manju_web/backend/services/workflow_runtime/video.py",
]

for file_path in files_to_fix:
    if not os.path.exists(file_path):
        print(f"⚠️ 文件不存在: {file_path}")
        continue
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    original_content = content
    
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
    
    # 3. 修复 actual_project_name 赋值
    # 将 actual_project_name = project_name or runtime_config.PROJECT_NAME
    # 改为 actual_project_name = project_name
    content = re.sub(
        r'actual_project_name = project_name or runtime_config\.PROJECT_NAME',
        'actual_project_name = project_name',
        content
    )
    
    # 4. 修复 proj 赋值
    # 将 proj = project_name or runtime_config.PROJECT_NAME
    # 改为 proj = project_name
    content = re.sub(
        r'proj = project_name or runtime_config\.PROJECT_NAME',
        'proj = project_name',
        content
    )
    
    if content != original_content:
        with open(file_path, 'w') as f:
            f.write(content)
        print(f"✓ 已修复: {os.path.basename(file_path)}")
    else:
        print(f"✓ 无需修复: {os.path.basename(file_path)}")

print("\n✓ 所有文件修复完成")
print("已修复所有 project_name or runtime_config.PROJECT_NAME 的模式")

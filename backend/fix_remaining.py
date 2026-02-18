#!/usr/bin/env python3
"""
修复剩余的 runtime_config.PROJECT_NAME 引用
"""

import re
from pathlib import Path

def main():
    file_path = Path("/Users/bytedance/Desktop/常见python/manju_web/backend/services/workflow_runtime/visual_audio_assets.py")
    content = file_path.read_text(encoding='utf-8')
    
    # 1. 修复所有 get_project_prefixes(runtime_config.PROJECT_NAME) 为 get_project_prefixes(project_name)
    # 但这需要函数有 project_name 参数
    
    # 统计剩余的 get_project_prefixes 调用
    remaining = content.count("get_project_prefixes(runtime_config.PROJECT_NAME)")
    print(f"需要修复的 get_project_prefixes 调用: {remaining}")
    
    # 策略：对于每个使用 get_project_prefixes(runtime_config.PROJECT_NAME) 的函数
    # 如果函数已经有 project_name 参数，则替换为 project_name
    # 否则添加 project_name 参数并替换
    
    # 简单策略：将所有 get_project_prefixes(runtime_config.PROJECT_NAME) 
    # 替换为 get_project_prefixes(project_name or runtime_config.PROJECT_NAME)
    content = content.replace(
        "get_project_prefixes(runtime_config.PROJECT_NAME)",
        "get_project_prefixes(project_name or runtime_config.PROJECT_NAME)"
    )
    
    # 2. 保存修改
    file_path.write_text(content, encoding='utf-8')
    
    # 3. 统计剩余的未修复引用
    remaining = content.count("runtime_config.PROJECT_NAME")
    print(f"\n剩余的 runtime_config.PROJECT_NAME 引用: {remaining}")
    print("修复完成!")

if __name__ == "__main__":
    main()

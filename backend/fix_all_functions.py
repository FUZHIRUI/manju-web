#!/usr/bin/env python3
"""
批量修复 visual_audio_assets.py 中所有函数的 project_name 参数
"""

import re
from pathlib import Path

def add_project_name_param(content: str, func_name: str, is_async: bool = False) -> str:
    """为函数添加 project_name 参数"""
    prefix = "async def " if is_async else "def "
    pattern = rf'{prefix}{func_name}\(([^)]*)\)'
    
    def replacer(match):
        params = match.group(1)
        if "project_name" in params:
            return match.group(0)  # 已经有project_name参数
        
        # 添加 project_name 参数
        if params.strip():
            new_params = params.rstrip() + ", project_name: Optional[str] = None"
        else:
            new_params = "project_name: Optional[str] = None"
        
        return f'{prefix}{func_name}({new_params})'
    
    return re.sub(pattern, replacer, content)

def fix_function_body(content: str, func_start: str, func_end: str = None) -> str:
    """修复函数体内的 project=runtime_config.PROJECT_NAME"""
    start_idx = content.find(func_start)
    if start_idx == -1:
        return content
    
    if func_end:
        end_idx = content.find(func_end, start_idx + len(func_start))
        if end_idx == -1:
            end_idx = len(content)
    else:
        # 找到下一个函数定义
        rest = content[start_idx + 1:]
        next_func = re.search(r'\n(async def |def )', rest)
        if next_func:
            end_idx = start_idx + 1 + next_func.start()
        else:
            end_idx = len(content)
    
    before = content[:start_idx]
    func_body = content[start_idx:end_idx]
    after = content[end_idx:]
    
    # 替换函数体内的 project=runtime_config.PROJECT_NAME
    func_body = func_body.replace("project=runtime_config.PROJECT_NAME", "project=project_name")
    
    return before + func_body + after

def main():
    file_path = Path("/Users/bytedance/Desktop/常见python/manju_web/backend/services/workflow_runtime/visual_audio_assets.py")
    content = file_path.read_text(encoding='utf-8')
    
    # 需要修复的函数列表 (函数名, 是否是async)
    functions_to_fix = [
        ("generate_images_with_qps", True),
        ("generate_location_images_shared", True),
        ("build_fenjing_prompts_with_retry", False),
        ("generate_cloth_images", False),
        ("generate_cloth_changed_images", False),
        ("build_character_prompts_with_retry", False),
        ("build_tts_prompts_for_chapter", False),
        ("build_location_prompts_with_retry", False),
        ("upload_jsonl_to_assets", False),
    ]
    
    # 1. 为每个函数添加 project_name 参数
    for func_name, is_async in functions_to_fix:
        content = add_project_name_param(content, func_name, is_async)
        print(f"添加参数到函数: {func_name}")
    
    # 2. 修复函数体内的 project=runtime_config.PROJECT_NAME
    for func_name, _ in functions_to_fix:
        # 找到函数定义
        for prefix in ["async def ", "def "]:
            func_def = f"{prefix}{func_name}("
            if func_def in content:
                content = fix_function_body(content, func_def)
                print(f"修复函数体: {func_name}")
                break
    
    # 3. 保存修改
    file_path.write_text(content, encoding='utf-8')
    
    # 4. 统计剩余的未修复引用
    remaining = content.count("project=runtime_config.PROJECT_NAME")
    print(f"\n剩余未修复的引用: {remaining}")
    print("修复完成!")

if __name__ == "__main__":
    main()

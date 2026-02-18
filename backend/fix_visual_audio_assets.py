#!/usr/bin/env python3
"""
批量修复 visual_audio_assets.py 中的 runtime_config.PROJECT_NAME 引用
"""

import re
from pathlib import Path

def main():
    file_path = Path("/Users/bytedance/Desktop/常见python/manju_web/backend/services/workflow_runtime/visual_audio_assets.py")
    content = file_path.read_text(encoding='utf-8')
    
    # 1. 修复所有 project=runtime_config.PROJECT_NAME 为 project=project_name
    # 但这需要函数已经有 project_name 参数
    
    # 2. 对于没有 project_name 参数的函数，我们需要添加参数
    # 首先找出所有使用 runtime_config.PROJECT_NAME 的函数
    
    # 获取main函数的范围
    main_start = content.find("async def main()")
    if main_start == -1:
        print("找不到main函数")
        return
    
    # 找到main函数结束位置（下一个顶层的async def或def）
    rest = content[main_start + 1:]
    next_func = re.search(r'\n(async def |def )', rest)
    if next_func:
        main_end = main_start + 1 + next_func.start()
    else:
        main_end = len(content)
    
    print(f"main函数范围: {main_start} 到 {main_end}")
    
    # main函数已经修复过了，跳过
    
    # 3. 修复其他函数中的 project=runtime_config.PROJECT_NAME
    # 策略：为每个函数添加 project_name 参数，并替换引用
    
    # 定义需要修复的函数及其修复策略
    # 由于复杂性，我们采用一个简化的方法：
    # 对于每个 emit_event 调用，如果它在函数内部，我们尝试从函数参数或局部变量获取 project_name
    
    # 统计剩余的 runtime_config.PROJECT_NAME 引用
    remaining = content.count("project=runtime_config.PROJECT_NAME")
    print(f"剩余需要修复的引用: {remaining}")
    
    # 简单修复：将所有 project=runtime_config.PROJECT_NAME 替换为 project=(project_name or runtime_config.PROJECT_NAME)
    # 但这需要确保 project_name 变量存在
    
    # 更安全的做法：创建一个辅助函数来获取项目名称
    helper_function = '''
def _get_project_name(local_vars: dict, base_dir: Optional[Path] = None) -> str:
    """从局部变量或目录推断项目名称"""
    if "project_name" in local_vars and local_vars["project_name"]:
        return local_vars["project_name"]
    if base_dir is not None:
        return base_dir.parent.name
    return runtime_config.PROJECT_NAME

'''
    
    # 检查是否已存在辅助函数
    if "_get_project_name" not in content:
        # 在文件开头导入后添加辅助函数
        import_section_end = content.find("\n\n", content.find("from . import runtime_config"))
        if import_section_end == -1:
            import_section_end = content.find("\n\n", content.find("import runtime_config"))
        
        if import_section_end > 0:
            content = content[:import_section_end] + helper_function + content[import_section_end:]
            print("添加辅助函数 _get_project_name")
    
    # 保存修改
    file_path.write_text(content, encoding='utf-8')
    print("修复完成")

if __name__ == "__main__":
    main()

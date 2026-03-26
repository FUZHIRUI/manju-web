# 清理 workflow_runtime 死代码

## Goal
清理 `manju_web/backend/services/workflow_runtime/` 中的垃圾代码和非活跃代码，修复已知的导入崩溃问题。

## Requirements
- 修复 `visual_audio/__init__.py` 中对不存在模块的导入（image_generation, audio_generation, asset_upload）
- 删除 `visual_audio/utils.py` 中 4 个未使用函数：read_json, slugify, format_duration, chunk_list
- 删除 `visual_audio/prompt_builders.py` 中 4 个未使用函数：load_prompt_template, format_prompt, build_tts_prompt, merge_prompt_parts
- 验证 `config.py` 是否为死代码（与 runtime_config.py 重复）

## Acceptance Criteria
- [ ] `visual_audio` 包可正常导入，无 ImportError
- [ ] 删除的函数确认无任何内部或外部引用
- [ ] 现有测试全部通过
- [ ] 外部调用方（server.py, workflow_service.py, asset_repo.py, project_utils.py）不受影响

## Technical Notes
- 分支：refactor/cleanup-dead-code
- 仅做删除操作，不改变任何业务逻辑
- config.py 如确认为死代码，标记但暂不删除（需进一步确认）

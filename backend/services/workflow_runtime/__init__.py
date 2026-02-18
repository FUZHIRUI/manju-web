"""
workflow_runtime 包 - 小说视频生成工作流运行时模块

【模块职责】
该包是整个小说转视频系统的核心工作流运行时，负责协调和管理从小说文本到最终视频的完整生成流程。

【执行顺序与流程】
1. auto_storyboard: 分镜自动生成 - 从小说提取角色、地点、摘要，生成分镜剧本
2. visual_audio_assets: 视听资产生成 - 生成角色图、地点图、分镜图、TTS音频
3. fenjing: 分镜图像生成 - 基于分镜提示词生成场景图片
4. video: 视频生成 - 基于分镜图和音频生成最终视频

【子模块说明】
- auto_storyboard: Phase 1/2 分镜剧本生成
- fenjing: 分镜图像生成与QC质检
- video: 视频任务创建、轮询、下载、上传
- visual_audio_assets: 角色/地点/服装图像 + TTS音频生成
- provider_runtime: API提供商统一封装(Ark/TTS/TOS)
- retry_runtime: 统一重试策略与错误分类
- runtime_config: 运行时配置管理
- io_jsonl: JSONL文件读写工具
- json_fields: JSON字段处理与映射
- json_parse: JSON解析与修复工具

【使用方式】
```python
from backend.services.workflow_runtime import auto_storyboard
auto_storyboard.run_workflow("novel.txt", phase="full")
```
"""

from . import auto_storyboard
from . import visual_audio_assets
from . import fenjing
from . import video

__all__ = ["auto_storyboard", "fenjing", "video", "visual_audio_assets"]

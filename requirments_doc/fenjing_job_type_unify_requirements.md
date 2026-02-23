# 需求文档：Fenjing Job Type 统一重构

## 1. 概述

### 1.1 背景
当前 `fenjing` 相关的工作流存在三个独立的 job type：`run_fenjing`、`run_fenjing_generate`、`run_fenjing_upload`，与 `auto_storyboard` 和 `visual_audio_assets` 的设计模式不一致（它们使用统一的 job type + phase 参数）。

### 1.2 目标
将 `fenjing` 的 job type 统一为 `run_fenjing`，通过 `phase` 参数区分步骤，与 `auto_storyboard` 和 `visual_audio_assets` 的设计模式保持一致。

## 2. EARS 需求分析

### 2.1 功能需求

#### FR-001: Job Type 统一
- **Event**: 当用户执行分镜相关操作时
- **Actor**: 系统
- **Request**: 将 `run_fenjing_generate` 和 `run_fenjing_upload` 的 job type 统一为 `run_fenjing`
- **Scope**: 后端 job_handler.py、workflow_service.py

**详细说明**:
- 移除 `run_fenjing_generate` 和 `run_fenjing_upload` 作为独立 job type
- 统一使用 `run_fenjing` 作为 job type
- 通过 `phase` 参数区分步骤：`generate_images`、`upload_assets`

#### FR-002: Phase 参数设计
- **Event**: 当前端调用分镜相关 API 时
- **Actor**: 前端用户
- **Request**: 使用 `phase` 参数指定执行步骤
- **Scope**: 后端 API、前端调用

**详细说明**:
- `phase=generate_images`：执行分镜图生成
- `phase=upload_assets`：执行分镜图上传
- `phase=all` 或不传：执行完整流程（下载+生成+上传）

#### FR-003: 前端 STAGE_TYPES 简化
- **Event**: 当前端渲染 job-item 卡片时
- **Actor**: 前端用户
- **Request**: `STAGE_TYPES` 只需包含 `fenjing`，无需 `fenjing_generate` 和 `fenjing_upload`
- **Scope**: 前端 app.js

**详细说明**:
- `STAGE_TYPES = ["auto_storyboard", "visual_audio_assets", "fenjing", "video"]`
- 移除 `fenjing_generate` 和 `fenjing_upload`

### 2.2 非功能需求

#### NFR-001: 一致性
- 与 `auto_storyboard` 和 `visual_audio_assets` 的设计模式保持一致

#### NFR-002: 向后兼容
- 旧的 API 调用方式需能正常工作（通过内部映射）

## 3. 影响评估

### 3.1 后端影响

| 文件 | 变更类型 | 影响描述 |
|------|----------|----------|
| `job_handler.py` | 修改 | 合并 workflow 路由，统一使用 `run_fenjing` |
| `workflow_service.py` | 修改 | 更新 `run_fenjing` 支持 phase 参数 |
| `status_service.py` | 修改 | 更新 workflow 到 flow 的映射 |

### 3.2 前端影响

| 文件 | 变更类型 | 影响描述 |
|------|----------|----------|
| `app.js` | 修改 | 简化 `STAGE_TYPES`，更新 API 调用 |

## 4. 设计对比

### 4.1 当前设计

```
前端调用:
- POST /api/projects/{project}/run/fenjing_generate
- POST /api/projects/{project}/run/fenjing_upload

后端 Job Type:
- run_fenjing_generate
- run_fenjing_upload
- run_fenjing
```

### 4.2 目标设计

```
前端调用:
- POST /api/projects/{project}/run/fenjing?phase=generate_images
- POST /api/projects/{project}/run/fenjing?phase=upload_assets

后端 Job Type:
- run_fenjing (统一)
```

### 4.3 与其他 Flow 对比

| Flow | Job Type | Phase 参数 |
|------|----------|------------|
| `auto_storyboard` | `run_auto_storyboard` | `phase1`, `phase2`, `step3_upload` |
| `visual_audio_assets` | `run_visual_audio_assets` | `all`, `download_assets`, `build_prompts`, `generate_images`, `generate_tts`, `upload_assets` 等 |
| `fenjing` | `run_fenjing` | `generate_images`, `upload_assets`, `all` |

## 5. 验收标准

### 5.1 功能验收
- [ ] `STAGE_TYPES` 只包含 `fenjing`，不包含 `fenjing_generate` 和 `fenjing_upload`
- [ ] 前端调用 `POST /api/projects/{project}/run/fenjing` 时使用 `phase` 参数
- [ ] 后端创建的 job type 统一为 `run_fenjing`
- [ ] 分镜生成按钮可正常点击并执行
- [ ] 分镜上传按钮可正常点击并执行
- [ ] job-item 卡片状态正确显示

### 5.2 非功能验收
- [ ] 与 `auto_storyboard` 和 `visual_audio_assets` 设计模式一致
- [ ] 旧的 API 调用方式仍能正常工作（向后兼容）

## 6. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| API 兼容性问题 | 低 | 中 | 保持旧 workflow 参数的内部映射 |
| 前端调用遗漏 | 中 | 低 | 全面搜索前端代码中的调用点 |

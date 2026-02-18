# Manju Web 工作流步骤定义

基于 `full_workflow_e2e_test_plan.md` 的完整工作流步骤定义。

## 完整工作流概览（18个步骤）

| 阶段 | 步骤 | 操作 | Flow | Phase | 前置条件 |
|------|------|------|------|-------|----------|
| **项目创建** | 1 | 创建新项目 | - | - | 无 |
| **阶段1** | 2 | 上传小说，执行剧本拆解 | auto_storyboard | phase1 | 步骤1完成 |
| **阶段2** | 3 | 执行分镜生成 | auto_storyboard | phase2 | 步骤2完成 |
| | 4 | 确认分镜文件生成 | - | - | 步骤3完成 |
| **阶段3** | 5 | 提示词生成 | visual_audio_assets | build_prompts | 步骤4完成 |
| | 6 | 图片生成 | visual_audio_assets | generate_images | 步骤5完成 |
| | 7 | TTS语音生成 | visual_audio_assets | generate_tts | 步骤6完成 |
| | 8 | 换装 | visual_audio_assets | cloth_images,cloth_changed | 步骤7完成 |
| | 9 | 上传资产 | visual_audio_assets | upload_assets | 步骤8完成 |
| **阶段4** | 10 | Batch页面点击分镜图生成 | fenjing | - | 步骤9完成 |
| | 11 | 点击任务栏卡片执行 | fenjing | - | 步骤10完成 |
| | 12 | 等待Fenjing生成完成 | fenjing | - | 步骤11完成 |
| **阶段5** | 13 | Batch页面点击视频生成 | video | - | 步骤12完成 |
| | 14 | 点击任务栏卡片执行 | video | - | 步骤13完成 |
| | 15 | 进入Videos页面观察 | video | - | 步骤14完成 |
| | 16 | 观察视频产物生成 | video | - | 步骤15完成 |
| | 17 | 验证任务完成 | video | - | 步骤16完成 |
| | 18 | 刷新验证 | - | - | 步骤17完成 |

## 各阶段详细说明

### 阶段1: 项目创建与剧本拆解

#### 步骤1: 创建项目
- **API**: `POST /api/projects`
- **请求体**: `{"project_name": "<project_name>"}`
- **成功标志**: HTTP 200
- **产物**: 项目目录创建

#### 步骤2: 上传小说并执行阶段1
- **API**: 
  - `POST /api/projects/{project}/upload-novel` (上传文件)
  - `POST /api/projects/{project}/execute` (触发执行)
- **请求体**: `{"flow": "auto_storyboard", "phase": "phase1", "chapter_size": 2500}`
- **等待条件**: `auto_storyboard.status == "completed"`
- **超时**: 5分钟
- **产物**: 
  - `manju_output/{project}/storyboard_assets/novel.txt`
  - `manju_output/{project}/storyboard_assets/chapters.jsonl`

### 阶段2: 分镜生成

#### 步骤3: 执行阶段2（分镜生成）
- **API**: `POST /api/projects/{project}/execute`
- **请求体**: `{"flow": "auto_storyboard", "phase": "phase2", "per_chapter_shots": 15}`
- **等待条件**: `auto_storyboard.status == "completed"`
- **超时**: 5分钟

#### 步骤4: 确认分镜文件生成
- **检查文件**: 
  - `manju_output/{project}/storyboard_assets/storyboards/storyboard_chapter_1.jsonl`
  - `manju_output/{project}/storyboard_assets/storyboards/storyboard_chapter_2.jsonl` (如果有多个章节)
- **成功标志**: 文件存在且不为空

### 阶段3: 角色与素材生成

#### 步骤5: 提示词生成
- **API**: `POST /api/projects/{project}/execute`
- **请求体**: `{"flow": "visual_audio_assets", "phase": "build_prompts"}`
- **等待条件**: 
  - `visual_audio_assets.steps.character_prompts == "completed"`
  - `visual_audio_assets.steps.location_prompts == "completed"`
  - `visual_audio_assets.steps.fenjing_prompts == "completed"`
- **超时**: 5分钟
- **产物**:
  - `manju_output/{project}/visual_audio_assets/prompts/character_prompts.jsonl`
  - `manju_output/{project}/visual_audio_assets/prompts/location_prompts.jsonl`
  - `manju_output/{project}/visual_audio_assets/prompts/fenjing_prompts.jsonl`

#### 步骤6: 图片生成
- **API**: `POST /api/projects/{project}/execute`
- **请求体**: `{"flow": "visual_audio_assets", "phase": "generate_images"}`
- **等待条件**:
  - `visual_audio_assets.steps.character_images == "completed"`
  - `visual_audio_assets.steps.location_images == "completed"`
- **超时**: 10分钟
- **产物**:
  - `manju_output/{project}/visual_audio_assets/images/character_*.png`
  - `manju_output/{project}/visual_audio_assets/images/location_*.png`

#### 步骤7: TTS语音生成
- **API**: `POST /api/projects/{project}/execute`
- **请求体**: `{"flow": "visual_audio_assets", "phase": "generate_tts"}`
- **等待条件**: `visual_audio_assets.steps.tts == "completed"`
- **超时**: 10分钟
- **产物**:
  - `manju_output/{project}/visual_audio_assets/tts/tts_chapter_*.jsonl`
  - `manju_output/{project}/visual_audio_assets/tts/*.mp3`

#### 步骤8: 换装
- **API**: `POST /api/projects/{project}/execute`
- **请求体**: `{"flow": "visual_audio_assets", "phase": "cloth_images,cloth_changed"}`
- **等待条件**:
  - `visual_audio_assets.steps.cloth_images == "completed"`
  - `visual_audio_assets.steps.cloth_changed == "completed"`
- **超时**: 5分钟
- **产物**:
  - `manju_output/{project}/visual_audio_assets/cloth/cloth_changed.jsonl`
  - `manju_output/{project}/visual_audio_assets/cloth/*.png`

#### 步骤9: 上传资产
- **API**: `POST /api/projects/{project}/execute`
- **请求体**: `{"flow": "visual_audio_assets", "phase": "upload_assets"}`
- **等待条件**: `visual_audio_assets.steps.upload_assets == "completed"`
- **超时**: 10分钟
- **产物**: 文件上传到TOS

### 阶段4: Fenjing图片生成

#### 步骤10: Batch页面点击分镜图生成按钮
- **前端操作**: Playwright点击"分镜图生成"按钮
- **页面**: Batch页面 (`/?project={project}&tab=batch`)
- **成功标志**: 任务栏卡片出现，状态为waiting

#### 步骤11: 点击任务栏卡片执行
- **前端操作**: Playwright点击任务卡片的"执行"按钮
- **成功标志**: 任务状态变为running

#### 步骤12: 等待Fenjing生成完成
- **等待条件**: `fenjing.status == "completed"`
- **超时**: 10分钟
- **产物**:
  - `manju_output/{project}/fenjing/fenjing_chapter_*.jsonl`
  - `manju_output/{project}/fenjing/fenjing_*.png`

### 阶段5: 视频生成

#### 步骤13: Batch页面点击视频生成按钮
- **前端操作**: Playwright点击"视频生成"按钮
- **页面**: Batch页面
- **成功标志**: 任务栏卡片出现，状态为waiting

#### 步骤14: 点击任务栏卡片执行视频生成
- **前端操作**: Playwright点击任务卡片的"执行"按钮
- **成功标志**: 任务状态变为running

#### 步骤15: 进入Videos页面观察生成过程
- **前端操作**: Playwright导航到Videos页面
- **页面**: Videos页面 (`/?project={project}&tab=videos`)
- **等待条件**: `video.steps.phase1_video_prompts == "completed"`
- **验证点**:
  - 左侧显示"分镜提示词"区域
  - 分镜提示词内容已生成

#### 步骤16: 观察视频产物生成
- **等待条件**:
  - `video.steps.phase2_video_generation == "completed"`
  - `video.steps.fenjing_video_upload == "completed"`
- **超时**: 20分钟
- **产物**:
  - `manju_output/{project}/video/videos/video_*.mp4`

#### 步骤17: 验证任务完成
- **检查点**:
  - `video.status == "completed"`
  - 视频文件存在且可播放
  - Batch页面任务卡片状态为completed

#### 步骤18: 刷新验证
- **前端操作**: Playwright刷新Batch和Videos页面
- **验证点**: 刷新后状态保持一致

## 状态流转规则

### Flow状态
- `waiting` -> `running` -> `completed`/`error`
- `partial_completed`: 部分步骤完成

### Step状态
- `waiting`: 等待执行
- `running`: 执行中
- `completed`: 完成
- `error`: 错误

### 状态检查API
```
GET /api/projects/{project}/flow-status
```

返回示例:
```json
{
  "auto_storyboard": {
    "status": "completed",
    "steps": {
      "phase1": "completed",
      "phase2": "completed",
      "upload": "completed"
    }
  },
  "visual_audio_assets": {
    "status": "partial_completed",
    "steps": {
      "character_prompts": "completed",
      "character_images": "running",
      ...
    }
  }
}
```

## 超时配置

| 阶段 | 默认超时 | 说明 |
|------|----------|------|
| 项目创建 | 30秒 | 快速操作 |
| 剧本拆解 | 5分钟 | 包含API调用 |
| 分镜生成 | 5分钟 | 包含API调用 |
| 提示词生成 | 5分钟 | 包含API调用 |
| 图片生成 | 10分钟 | 包含图片生成时间 |
| TTS生成 | 10分钟 | 包含语音合成时间 |
| 换装 | 5分钟 | 包含图片生成 |
| 上传 | 10分钟 | 包含网络传输 |
| Fenjing生成 | 10分钟 | 包含图片生成 |
| 视频生成 | 20分钟 | 包含视频合成时间 |

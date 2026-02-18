---
name: manju-workflow-e2e-test
description: |
  Manju Web端到端工作流测试技能。通过VLM截图验证方式，按照18个步骤顺序执行完整工作流，
  包括：项目创建→剧本拆解→分镜生成→角色与素材生成→Fenjing生成→视频生成。
  支持前端模拟操作、VLM智能验证、结果收集和异常自动恢复。
tools:
  - name: manju-verifier
    description: 用于验证每个步骤的执行结果
  - name: bug-fixer
    description: 遇到严重问题时调用排查
---

# Manju Web Workflow E2E Test 技能使用指南

## 技能能做什么？

### 核心功能

本技能通过**VLM截图验证**方式，按照**18个步骤**执行完整的Manju Web工作流：

```
1️⃣ 创建项目
    ↓
2️⃣ 上传小说，执行剧本拆解（step1）
    ↓
3️⃣ 执行分镜生成（step2）
    ↓
4️⃣ 确认分镜文件生成
    ↓
5️⃣ 上传资产到TOS（step3_upload）
    ↓
6️⃣ 提示词生成（character_prompts, location_prompts, fenjing_prompts）
    ↓
7️⃣ 图片生成（character_images, location_images）
    ↓
8️⃣ TTS语音生成
    ↓
9️⃣ 换装（cloth_images, cloth_changed）
    ↓
🔟 上传资产到TOS（visual_audio_assets）
    ↓
1️⃣1️⃣ Batch页面点击分镜图生成按钮
    ↓
1️⃣2️⃣ 点击任务栏卡片执行Fenjing
    ↓
1️⃣3️⃣ 等待Fenjing生成完成
    ↓
1️⃣4️⃣ Batch页面点击视频生成按钮
    ↓
1️⃣5️⃣ 点击任务栏卡片执行视频生成
    ↓
1️⃣6️⃣ 进入Videos页面观察生成过程
    ↓
1️⃣7️⃣ 观察视频产物生成
    ↓
1️⃣8️⃣ 验证任务完成
    ↓
1️⃣9️⃣ 刷新验证状态一致性
```

### 额外功能

1. **VLM智能验证**：通过VLM模型分析截图，自动验证页面状态
2. **结果自动收集**：自动收集API响应、日志、产物文件、截图
3. **异常自动恢复**：遇到问题时自动诊断并尝试恢复
4. **Bug Fixer联动**：严重问题时自动调用bug-fixer技能排查

## 怎么用？

### 前提：服务启动

```bash
kill -9 $(lsof -t -i :8086)
cd /Users/bytedance/Desktop/常见python/manju_web && pkill -f "python.*server\.py" 2>/dev/null; sleep 2; cd backend && python server.py > logs/server_latest.log 2>&1 &
```


### 方式: 命令行执行单个步骤

```bash
cd /Users/bytedance/Desktop/常见python/manju_web/skills/manju-workflow-e2e-test

# 步骤1-2: 创建项目并执行step1
python scripts/e2e_test.py \
    --mode vlm \
    --project "e2e_test_$(date +%Y%m%d_%H%M%S)" \
    --base-url http://127.0.0.1:8086 \
    --vlm-base-url https://ark.cn-beijing.volces.com/api/v3 \
    --api-key 58556eed-a35b-4e01-a30c-6736894afb42 \
    --model ep-20260215001006-86n7g \
    --flow auto_storyboard \
    --phase step1 \
    --action-label "步骤 1" \
    --wait-steps step1 \
    --novel-path /Users/bytedance/Desktop/常见python/manju_web/backend/tests/novel.txt \
    --chapter-size 2500 \
    --vlm-task extract

# 步骤3-4: 执行step2
python scripts/e2e_test.py \
    --mode vlm \
    --project "e2e_test_project" \
    --base-url http://127.0.0.1:8086 \
    --vlm-base-url https://ark.cn-beijing.volces.com/api/v3 \
    --api-key 58556eed-a35b-4e01-a30c-6736894afb42 \
    --model ep-20260215001006-86n7g \
    --flow auto_storyboard \
    --phase step2 \
    --action-label "步骤 2" \
    --wait-steps step2 \
    --per-chapter-shots 15 \
    --vlm-task extract

# 步骤5: 执行step3_upload
python scripts/e2e_test.py \
    --mode vlm \
    --project "e2e_test_project" \
    --base-url http://127.0.0.1:8086 \
    --vlm-base-url https://ark.cn-beijing.volces.com/api/v3 \
    --api-key 58556eed-a35b-4e01-a30c-6736894afb42 \
    --model ep-20260215001006-86n7g \
    --flow auto_storyboard \
    --phase step3_upload \
    --action-label "步骤 3" \
    --wait-steps step3_upload \
    --vlm-task extract
```

## 每一步具体做什么？

### 阶段1: 项目创建与剧本拆解（步骤1-2）

**步骤1: 创建项目**
- **每次从步骤1开始的时候，都要先按时间戳创建一个新的项目。**
- **操作**: 调用 `POST /api/projects` 创建新项目
- **预期结果**:
  - API返回HTTP 200
  - 项目目录 `manju_output/{project_name}/` 创建成功
- **结果获取方式**:
  - API响应：检查HTTP状态码
  - 文件系统：检查 `manju_output/{project_name}/` 是否存在

**步骤2: 上传小说，执行剧本拆解（step1）**
- **操作**:
  - 使用Playwright打开 `/?project={project}&tab=batch`
  - 点击"步骤 1"按钮
  - **将 `storyboard_assets/novel.txt` 的内容，通过复制粘贴的方式贴入文本框。**
  - 触发 `auto_storyboard` flow的 `step1`
  - 等待 `auto_storyboard.steps.step1` 和 `auto_storyboard.steps.step1_extract` 变为 `completed`（超时5分钟）
- **预期结果**:
  - `auto_storyboard.steps.step1` → `completed`
  - `auto_storyboard.steps.step1_extract` → `completed`
  - 在页面上，可见步骤1的点击按钮变为'重生',步骤2的按钮可运行
  - `storyboard_assets/characters.jsonl` 文件存在且有效
  - `storyboard_assets/summaries.jsonl` 文件存在且有效
  - `storyboard_assets/locations.jsonl` 文件存在且有效
- **结果获取方式**:
  - API: `GET /api/projects/{project}/flow-status`
  - 文件系统：检查上述文件是否存在
  - VLM验证：截图验证页面状态
  - JSON验证：用 `python -m json.tool` 验证JSON文件

### 阶段2: 分镜生成（步骤3-4）

**步骤3: 执行分镜生成（step2）**
- **操作**:
  - 使用Playwright点击"步骤 2"按钮
  - 触发 `auto_storyboard` flow的 `step2`
  - 等待 `auto_storyboard.steps.step2` 和 `auto_storyboard.steps.step2_storyboard` 变为 `completed`（超时5分钟）
- **预期结果**:
  - `auto_storyboard.steps.step2` → `completed`
  - `auto_storyboard.steps.step2_storyboard` → `completed`
  - **中间态要关注：在分镜生成运行过程中，通过flow_status获取 `auto_storyboard.steps.step1` 保持为`completed`**
  - 执行前后，flow_status获取 `auto_storyboard.steps.step1` 保持为`completed`
  - 在页面上，可见步骤2和步骤1的点击按钮变为'重生'
- **结果获取方式**:
  - API: `GET /api/projects/{project}/flow-status`
  - VLM验证：截图验证页面状态
- 如遇非预期状态，原地用bug技能排查。

**步骤4: 确认分镜文件生成**
- **操作**:
  - 检查 `storyboard_assets/storyboards/storyboard*.jsonl` 文件存在
  - 验证JSON文件有效
- **预期结果**:
  - `storyboard_assets/storyboards/storyboard*.jsonl` 文件存在
  - 文件大小 > 0
  - JSON格式有效
- **结果获取方式**:
  - 文件系统：检查文件是否存在
  - 文件大小：`ls -lh` 查看大小
  - JSON验证：`python -m json.tool < file.jsonl`

### 阶段3: 上传资产（步骤5）

**步骤5: 上传资产到TOS（step3_upload）**
- **操作**:
  - 使用Playwright点击"步骤 3"按钮
  - 触发 `auto_storyboard` flow的 `step3_upload`
  - 等待 `auto_storyboard.steps.step3_upload` 和 `auto_storyboard.steps.step3_upload_assets` 变为 `completed`（超时10分钟）
- **预期结果**:
  - `auto_storyboard.steps.step3_upload` → `completed`
  - `auto_storyboard.steps.step3_upload_assets` → `completed`
  - `auto_storyboard.status` → `completed`
  - 在页面上，步骤1、步骤2、步骤3的按钮都置灰不可点击
  - 日志中显示资产上传成功信息
- **结果获取方式**:
  - API: `GET /api/projects/{project}/flow-status`
  - 日志：`grep "upload" backend/logs/*.log`
  - VLM验证：截图验证页面状态

### 阶段4: 角色与素材生成（步骤6-10）

**步骤6: 提示词生成**
- **操作**:
  - 使用Playwright点击"第一步：提示词"按钮
  - 触发 `visual_audio_assets` flow的 `build_prompts`
  - 等待以下步骤全部完成（超时5分钟）：
    - `character_prompts` → completed
    - `location_prompts` → completed
    - `fenjing_prompts` → completed
- **预期结果**:
  - `visual_audio_assets.status` → `partial_completed`
  - `character_prompts` → `completed`
  - `location_prompts` → `completed`
  - `fenjing_prompts` → `completed`
  - 在页面上，第一步 提示词的按钮置灰不可点击，准备资产，角色提示词，地点提示词，分镜提示词状态为已完成
  - `visual_audio_assets/prompts/character_prompts.jsonl` 存在
  - `visual_audio_assets/prompts/location_prompts.jsonl` 存在
  - `visual_audio_assets/prompts/fenjing_prompts.jsonl` 存在
- **结果获取方式**:
  - API: `GET /api/projects/{project}/flow-status`
  - 文件系统：检查上述文件是否存在
  - VLM验证：截图验证页面状态

**步骤7: 图片生成**
- **操作**:
  - 使用Playwright点击"第二步：生成"按钮
  - 触发 `visual_audio_assets` flow的 `generate_images`
  - 等待以下步骤全部完成（超时10分钟）：
    - `character_images` → completed
    - `location_images` → completed
  - 在生成过程中，flow_status的 
    -- `character_prompts` 保持 completed
    -- `location_prompts` 保持 completed
    -- `fenjing_prompts` 保持 completed
- **预期结果**:
  - `character_images` → `completed`
  - `location_images` → `completed`
  - 在页面上，第一步 提示词以及第二步 生成的按钮置灰不可点击，准备资产，角色提示词，地点提示词，分镜提示词，角色图，地点图状态为已完成
  - `visual_audio_assets/images/character_*.png` 文件存在（至少1个）
  - `visual_audio_assets/images/location_*.png` 文件存在（至少1个）
  - 图片文件大小 > 0
- **结果获取方式**:
  - API: `GET /api/projects/{project}/flow-status`
  - 文件系统：`ls visual_audio_assets/images/` 查看文件
  - 图片查看：用图片查看器确认图片可正常显示
  - VLM验证：截图验证页面状态
- 如遇非预期状态，原地用bug技能排查。

**步骤8: TTS语音生成**
- **操作**:
  - 使用Playwright点击"第二步：TTS语音"按钮
  - 触发 `visual_audio_assets` flow的 `generate_tts`
  - 等待 `tts` → completed（超时10分钟）
- **预期结果**:
  - `tts` → `completed`
  - `visual_audio_assets/tts/tts_chapter_*.jsonl` 文件存在
  - 在页面上，第一步 提示词以及第二步 生成，第二步 TTS语音的按钮置灰不可点击，准备资产，角色提示词，地点提示词，分镜提示词，角色图，地点图，TTS语音状态为已完成
  - `visual_audio_assets/tts/*.mp3` 文件存在（至少1个）
  - MP3文件大小 > 0
- **结果获取方式**:
  - API: `GET /api/projects/{project}/flow-status`
  - 文件系统：`ls visual_audio_assets/tts/` 查看文件
  - 音频播放：用音频播放器确认MP3可正常播放
  - VLM验证：截图验证页面状态

**步骤9: 换装**
- **操作**:
  - 使用Playwright点击"第三步：换装"按钮
  - 触发 `visual_audio_assets` flow的 `cloth_images,cloth_changed`
  - 等待以下步骤全部完成（超时5分钟）：
    - `cloth_images` → completed
    - `cloth_changed` → completed
- **预期结果**:
  - `cloth_images` → `completed`
  - `cloth_changed` → `completed`
  - 在页面上，第一步 提示词以及第二步 生成，第二步 TTS语音，第三步 换装的按钮置灰不可点击，准备资产，角色提示词，地点提示词，分镜提示词，角色图，地点图，TTS语音，服装与换装的状态为已完成
  - `visual_audio_assets/cloth/cloth_changed.jsonl` 文件存在
  - `visual_audio_assets/cloth/*.png` 文件存在（可能有，也可能没有，取决于是否有换装目标）
- **结果获取方式**:
  - API: `GET /api/projects/{project}/flow-status`
  - 文件系统：检查上述文件是否存在
  - VLM验证：截图验证页面状态

**步骤10: 上传资产（visual_audio_assets）**
- **操作**:
  - 使用Playwright点击"第四步：上传"按钮
  - 触发 `visual_audio_assets` flow的 `upload_assets`
  - 等待 `upload_assets` → completed（超时10分钟）
- **预期结果**:
  - `upload_assets` → `completed`
  - `visual_audio_assets/upload/upload_complete.marker` 文件存在（如果有）
  - 在页面上，第一步 提示词以及第二步 生成，第二步 TTS语音，第三步 换装，第四步 上传的按钮置灰不可点击，准备资产，角色提示词，地点提示词，分镜提示词，角色图，地点图，TTS语音，服装与换装，上传资产的状态为已完成
  - 日志中显示 "All assets uploaded successfully"
- **结果获取方式**:
  - API: `GET /api/projects/{project}/flow-status`
  - 文件系统：检查marker文件是否存在
  - 日志：`grep "upload" backend/logs/*.log`
  - VLM验证：截图验证页面状态

### 阶段5: Fenjing图片生成（步骤11-13）

**步骤11: Batch页面点击分镜图生成按钮**
- **操作**:
  - 使用Playwright打开 `/?project={project}&tab=batch`
  - 点击"分镜图生成"按钮
  - 截图验证：任务栏卡片出现，状态为waiting
- **预期结果**:
  - 任务栏卡片出现，显示"分镜图生成"
  - 任务状态为 `waiting`
  - 截图中可以看到任务卡片
- **结果获取方式**:
  - Playwright截图：自动保存到 `manju_output/{project}/screenshots/`
  - VLM验证：验证截图中的任务卡片状态
  - 人工查看：打开截图确认

**步骤12: 点击任务栏卡片执行Fenjing**
- **操作**:
  - 使用Playwright点击任务卡片的"执行"按钮
  - 截图验证：任务状态从waiting变为running
- **预期结果**:
  - 任务状态从 `waiting` 变为 `running`
  - "执行"按钮变为"执行中"或禁用
  - 截图中可以看到状态变化
- **结果获取方式**:
  - Playwright截图：自动保存截图
  - VLM验证：对比前后截图验证状态变化
  - 人工查看：对比前后截图确认状态变化

**步骤13: 等待Fenjing生成完成**
- **操作**:
  - 等待 `fenjing.status` 变为 `completed`（超时10分钟）
  - 截图验证：任务状态变为completed
- **预期结果**:
  - `fenjing.status` → `completed`
  - `fenjing/fenjing_chapter_*.jsonl` 文件存在
  - 在页面上，分镜图生成，生成分镜图，上传资产全部变为已完成，执行按钮不可点击，置灰
  - `fenjing/fenjing_*.png` 文件存在（至少1个）
  - 图片文件大小 > 0
- **结果获取方式**:
  - API: `GET /api/projects/{project}/flow-status`
  - 文件系统：`ls fenjing/` 查看文件
  - 图片查看：用图片查看器确认图片可正常显示
  - VLM验证：截图验证页面状态

### 阶段6: 视频生成（步骤14-19）

**步骤14: Batch页面点击视频生成按钮**
- **操作**:
  - 使用Playwright打开Batch页面
  - 点击"视频生成"按钮
  - 截图验证：任务栏卡片出现，状态为waiting
- **预期结果**:
  - 任务栏卡片出现，显示"视频生成"
  - 任务状态为 `waiting`
  - 截图中可以看到任务卡片
- **结果获取方式**:
  - Playwright截图：自动保存截图
  - VLM验证：验证截图中的任务卡片状态
  - 人工查看：打开截图确认

**步骤15: 点击任务栏卡片执行视频生成**
- **操作**:
  - 使用Playwright点击任务卡片的"执行"按钮
  - 截图验证：任务状态从waiting变为running
- **预期结果**:
  - 任务状态从 `waiting` 变为 `running`
  - "执行"按钮变为"执行中"或禁用
  - 截图中可以看到状态变化
- **结果获取方式**:
  - Playwright截图：自动保存截图
  - VLM验证：对比前后截图验证状态变化
  - 人工查看：对比前后截图确认状态变化

**步骤16: 进入Videos页面观察生成过程**
- **操作**:
  - 使用Playwright导航到 `/?project={project}&tab=videos`
  - 等待 `video.steps.phase1_video_prompts` → completed（超时5分钟）
  - 截图验证：左侧显示"分镜提示词"区域
- **预期结果**:
  - 页面左侧显示"分镜提示词"区域
  - 分镜提示词内容已填充
  - `video.steps.phase1_video_prompts` → `completed`
- **结果获取方式**:
  - Playwright截图：自动保存截图
  - VLM验证：验证截图中的分镜提示词显示
  - 人工查看：查看截图确认分镜提示词显示
  - API: `GET /api/projects/{project}/flow-status`

**步骤17: 观察视频产物生成**
- **操作**:
  - 等待以下步骤全部完成（超时20分钟）：
    - `video.steps.phase2_video_generation` → completed
    - `video.steps.fenjing_video_upload` → completed
  - 截图验证：右侧出现视频缩略图
- **预期结果**:
  - `video.steps.phase2_video_generation` → `completed`
  - `video.steps.fenjing_video_upload` → `completed`
  - 页面右侧出现视频缩略图
  - 视频数量与分镜数一致
- **结果获取方式**:
  - Playwright截图：自动保存截图
  - VLM验证：验证截图中的视频缩略图显示
  - 人工查看：查看截图确认视频缩略图显示
  - API: `GET /api/projects/{project}/flow-status`

**步骤18: 验证任务完成**
- **操作**:
  - 检查 `video.status` → completed
  - 验证视频文件存在：`video/videos/*.mp4`
  - 返回Batch页面，截图验证：任务卡片状态为completed
- **预期结果**:
  - `video.status` → `completed`
  - `video/videos/*.mp4` 文件存在（至少1个）
  - MP4文件大小 > 0
  - Batch页面任务卡片状态为 `completed`
- **结果获取方式**:
  - API: `GET /api/projects/{project}/flow-status`
  - 文件系统：`ls video/videos/` 查看文件
  - 视频播放：用视频播放器确认MP4可正常播放
  - Playwright截图：自动保存截图
  - VLM验证：验证截图中的任务状态

**步骤19: 刷新验证**
- **操作**:
  - 使用Playwright刷新Batch页面
  - 使用Playwright刷新Videos页面
  - 截图验证：刷新后状态保持一致
- **预期结果**:
  - 刷新后所有状态保持一致
  - 已完成的步骤仍然显示为completed
  - 视频产物仍然存在
- **结果获取方式**:
  - Playwright截图：刷新前后各截图一张
  - VLM验证：对比截图确认状态一致
  - 人工查看：对比截图确认状态一致
  - API: 刷新后再次调用 `GET /api/projects/{project}/flow-status` 确认

## VLM验证模式说明

### VLM任务类型

1. **extract模式**：抽取任务卡片信息
   ```bash
   --vlm-task extract
   ```
   输出JSON格式：
   ```json
   {
     "flow": "auto_storyboard",
     "project": "e2e_test_project",
     "steps": [
       {"label": "阶段 1", "status": "completed", "progress": ""},
       {"label": "阶段 2", "status": "waiting", "progress": ""}
     ]
   }
   ```

2. **check模式**：验证页面状态是否符合预期
   ```bash
   --vlm-task check
   ```
   输出JSON格式：
   ```json
   {
     "passed": true,
     "details": "阶段1已完成，阶段2等待中，符合预期",
     "evidence": "截图显示阶段1按钮为'重生'，阶段2按钮可点击"
   }
   ```

### VLM兜底操作机制

当常规的 Playwright 点击操作失败时（如按钮文字变更、布局调整），技能会自动启用 **VLM 兜底机制**：

```
常规点击失败 → 截图 → VLM分析 → 获取按钮位置 → 执行点击
```

**工作原理**：
1. 尝试使用预设的按钮文字进行点击
2. 如果失败，截取当前页面截图
3. 调用 VLM 分析截图，识别目标按钮的准确文字和位置
4. 根据 VLM 指导尝试点击（支持备选按钮）
5. 返回点击结果和 VLM 分析详情

**VLM 返回格式**：
```json
{
  "analysis": "页面分析简述",
  "target_button_text": "按钮准确文字",
  "target_button_location": "按钮位置描述",
  "alternative_buttons": ["备选按钮1", "备选按钮2"],
  "confidence": "high/medium/low",
  "reasoning": "选择该按钮的理由"
}
```

**优势**：
- 无需修改技能即可适应前端 UI 变更
- 自动处理按钮文字、位置的变化
- 支持备选方案，提高成功率
- 禁用 thinking 模式，响应更快

### VLM验证点

| 步骤 | VLM验证内容 |
|------|------------|
| 步骤2 | 步骤1按钮变为"重生"，步骤2按钮可运行 |
| 步骤3 | 步骤1和步骤2按钮都变为"重生"，步骤3按钮可运行 |
| 步骤5 | 步骤1/2/3按钮都置灰，上传资产状态为已完成 |
| 步骤6 | 提示词按钮置灰，准备资产/角色提示词/地点提示词/分镜提示词为已完成 |
| 步骤7 | 提示词和生成按钮置灰，角色图/地点图为已完成 |
| 步骤8 | 提示词/生成/TTS按钮置灰，TTS语音为已完成 |
| 步骤9 | 换装按钮置灰，服装与换装为已完成 |
| 步骤10 | 上传按钮置灰，上传资产为已完成 |
| 步骤11-12 | 任务卡片状态从waiting变为running |
| 步骤13 | 分镜图生成任务状态为completed |
| 步骤14-15 | 视频生成任务卡片状态从waiting变为running |
| 步骤16 | Videos页面左侧显示分镜提示词 |
| 步骤17 | Videos页面右侧显示视频缩略图 |
| 步骤18 | Batch页面视频生成任务状态为completed |
| 步骤19 | 刷新后状态保持一致 |

## 遇到问题怎么办？

### 自动恢复（技能会自动处理）

| 问题 | 技能自动做什么 |
|------|----------------|
|浏览器打开后，访问链接失败|服务崩溃，调用bug修复子智能体与技能进行深度定位问题点|
|进行到某步骤后，页面可访问，但是状态处于失败状态|重试2次后，若仍失败，调用bug修复子智能体技能先定位问题点，再与用户确认是否需要修复|
| 服务未运行（Connection refused） | 自动重启服务 |
| 超时（Timeout） | 超时时间翻倍后重试 |
| TOS Presign失败 | 检查TOS配置 |

### 需要人工介入（调用bug-fixer）

| 问题 | 技能自动做什么 |
|------|----------------|
| Print I/O错误（I/O operation on closed file） | 生成bug报告，建议调用bug-fixer |
| 状态重置错误（completed变running） | 生成bug报告，建议调用bug-fixer |
| 代码修复后 | 人工确认后续操作 |
### Bug报告包含什么？

- 问题类型和严重程度
- 诊断详情（日志、截图、API响应）
- 建议操作
- 相关文件列表
- 报告保存路径

## 配置选项

```python
# e2e_test.py 参数说明
--mode vlm                    # 使用VLM验证模式
--project PROJECT_NAME        # 项目名称
--base-url URL               # 后端服务地址
--vlm-base-url URL           # VLM服务地址
--api-key KEY                # API密钥
--model MODEL                # VLM模型名称
--flow FLOW                  # flow名称 (auto_storyboard/visual_audio_assets/fenjing/video)
--phase PHASE                # phase名称 (step1/step2/step3_upload/build_prompts/generate_images/generate_tts/cloth_changed/upload_assets)
--action-label LABEL         # 操作按钮标签 (步骤 1/步骤 2/步骤 3/第一步：提示词/第二步：生成/第二步：TTS语音/第三步：换装/第四步：上传)
--wait-steps STEPS           # 等待完成的步骤，逗号分隔
--wait-timeout SECONDS       # 等待超时时间（默认120秒）
--novel-path PATH            # 小说文件路径
--chapter-size SIZE          # 章节字数（phase1使用）
--per-chapter-shots NUM      # 每章分镜数（phase2使用）
--vlm-task TASK              # VLM任务类型 (extract/check)
--headless                   # 无头模式运行
```

## 核心组件说明

### e2e_test.py

**作用**：VLM验证执行器，执行单个步骤并验证结果

**主要功能**：
- 启动Playwright浏览器
- 执行前端操作（点击按钮、填写表单）
- 截取执行前/执行后/刷新后三张截图
- 调用VLM模型分析截图
- 输出验证结果

### PlaywrightController

**作用**：前端模拟控制器，模拟用户点击操作

**主要功能**：
- 点击"分镜图生成"按钮
- 点击"视频生成"按钮
- 点击任务卡片执行按钮
- 截图验证页面状态

### 结果收集

**截图保存路径**：
```
manju_output/{project_name}/screenshots/
├── {action_name}_before_{timestamp}.png      # 执行前截图
├── {action_name}_after_{timestamp}.png       # 执行后截图
└── {action_name}_refresh_{timestamp}.png     # 刷新后截图
```

## 参考文档

- [完整测试方案](/Users/bytedance/Desktop/常见python/manju_web/requirments_doc/full_workflow_e2e_test_plan.md) - 原始需求文档
- [e2e_test.py](/Users/bytedance/Desktop/常见python/manju_web/skills/manju-workflow-e2e-test/scripts/e2e_test.py) - VLM验证执行脚本
- [playwright_controller.py](/Users/bytedance/Desktop/常见python/manju_web/skills/manju-workflow-e2e-test/scripts/playwright_controller.py) - 前端控制器

## 鉴权配置

VLM服务需要以下环境变量或参数：
- `ARK_API_KEY`: API密钥
- `ARK_VLM_MODEL`: VLM模型名称
- `ARK_VLM_BASE_URL`: VLM服务基础URL

默认配置：
- API Key: `58556eed-a35b-4e01-a30c-6736894afb42`
- Model: `ep-20260215001006-86n7g`
- Base URL: `https://ark.cn-beijing.volces.com/api/v3`

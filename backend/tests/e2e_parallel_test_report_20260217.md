# E2E并行测试报告

**测试时间**: 2026-02-17  
**测试项目**: 
- Agent A: `e2e_agent_a_20260217_193639`
- Agent B: `e2e_agent_b_20260217_193642`

---

## 测试执行摘要

| 步骤 | 描述 | Agent A | Agent B | 状态 |
|------|------|---------|---------|------|
| 1 | 创建项目 | ✅ | ✅ | 成功 |
| 2 | 剧本拆解(step1) | ✅ completed | ✅ completed | 成功 |
| 3 | 分镜生成(step2) | ✅ completed | ✅ completed | 成功 |
| 4 | 上传资产到TOS(step3_upload) | ✅ completed | ✅ completed | 成功 |
| 5 | 提示词生成(build_prompts) | ❌ error | ❌ error | **失败** |
| 6 | 图片生成 | - | - | 未执行 |
| 7 | TTS语音生成 | - | - | 未执行 |
| 8 | 换装 | - | - | 未执行 |
| 9 | 上传资产 | - | - | 未执行 |
| 10 | Fenjing图片生成 | - | - | 未执行 |
| 11 | 视频生成 | - | - | 未执行 |

---

## 详细执行记录

### 步骤1: 创建项目
- **执行时间**: 2026-02-17 19:36
- **Agent A项目**: `e2e_agent_a_20260217_193639`
- **Agent B项目**: `e2e_agent_b_20260217_193642`
- **结果**: 两个项目均成功创建，目录结构正确

### 步骤2: 剧本拆解(step1)
- **执行时间**: 2026-02-17 19:36:53 - 19:37:22
- **Agent A结果**: 
  - step1: completed
  - step1_extract: completed
- **Agent B结果**:
  - step1: completed
  - step1_extract: completed
- **产物验证**: characters.jsonl, locations.jsonl, summaries.jsonl 文件生成成功

### 步骤3: 分镜生成(step2)
- **执行时间**: 2026-02-17 19:39:50 - 19:44
- **Agent A结果**:
  - step2: completed
  - step2_storyboard: completed
  - step1保持: completed ✅
- **Agent B结果**:
  - step2: completed
  - step2_storyboard: completed
  - step1保持: completed ✅
- **产物验证**: storyboards目录下分镜文件生成成功

### 步骤4: 上传资产到TOS(step3_upload)
- **执行时间**: 2026-02-17 20:02:24 - 20:08:05
- **Agent A结果**:
  - step3_upload: completed
  - step3_upload_assets: completed
  - auto_storyboard.status: completed
- **Agent B结果**:
  - step3_upload: completed
  - step3_upload_assets: completed
  - auto_storyboard.status: completed
- **注意**: 按钮文字为"运行"而非"步骤 3"，已通过VLM检测找到并点击

### 步骤5: 提示词生成(build_prompts)
- **执行时间**: 2026-02-17 20:08:20
- **Agent A结果**: ❌ error
- **Agent B结果**: ❌ error
- **错误原因**: 
  ```
  visual_audio_assets flow在下载资产时使用了错误的路径：
  - 实际路径: manju/{project_name}/assets/characters.jsonl
  - 错误路径: manju/default/assets/characters.jsonl
  ```
- **错误日志**:
  ```json
  {
    "error": "The specified key does not exist.",
    "code": "NoSuchKey",
    "request_url": "https://fzruse.tos-cn-beijing.volces.com/manju/default/assets/characters.jsonl"
  }
  ```

---

## 发现的问题

### 🐛 Bug: visual_audio_assets TOS路径错误

**问题描述**: 
visual_audio_assets流程在下载资产时，使用了硬编码的路径 `manju/default/assets`，而不是根据项目名称动态生成的路径 `manju/{project_name}/assets`。

**影响范围**:
- 所有使用visual_audio_assets flow的项目都会失败
- 无法执行步骤4-8（提示词生成、图片生成、TTS、换装、上传）

**建议修复**:
在 `visual_audio_assets.py` 中使用 `get_project_prefixes(project_name)` 获取正确的TOS前缀，而不是使用默认的 `manju/default/assets`。

---

## 测试环境

- **服务地址**: http://127.0.0.1:8086
- **VLM服务**: https://ark.cn-beijing.volces.com/api/v3
- **TOS Bucket**: fzruse
- **测试小说**: /Users/bytedance/Desktop/常见python/manju_web/backend/tests/novel.txt

---

## 结论

1. **步骤1-3执行成功**: 剧本拆解、分镜生成、上传TOS三个步骤在两个并行Agent中都成功完成
2. **步骤4失败**: 由于系统Bug导致visual_audio_assets无法正确下载TOS资产
3. **并行测试验证**: 两个Agent可以并行执行，不会相互干扰
4. **建议**: 修复visual_audio_assets的TOS路径问题后，重新执行完整E2E测试

---

## 附件

- Agent A日志: `/tmp/agent_a_step*.log`
- Agent B日志: `/tmp/agent_b_step*.log`
- 截图目录: `/Users/bytedance/Desktop/常见python/manju_web/skills/manju-workflow-e2e-test/output/`

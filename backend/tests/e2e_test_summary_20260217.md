# E2E并行测试执行总结

**测试时间**: 2026-02-17  
**测试项目**: manju-workflow-e2e-test

---

## 测试执行概况

### 第一轮测试（修复前）
- **Agent A 项目**: `e2e_agent_a_20260217_193639`
- **Agent B 项目**: `e2e_agent_b_20260217_193639`

| 步骤 | Agent A | Agent B | 结果 |
|------|---------|---------|------|
| 步骤1: 剧本拆解(step1) | ✅ completed | ✅ completed | 成功 |
| 步骤2: 分镜生成(step2) | ✅ completed | ✅ completed | 成功 |
| 步骤3: 上传TOS(step3_upload) | ✅ completed | ✅ completed | 成功 |
| 步骤4: 提示词生成(build_prompts) | ❌ error | ❌ error | **失败** |

**失败原因**: visual_audio_assets 使用了错误的TOS路径 `manju/default/assets`，而不是 `manju/{project_name}/assets`

---

## Bug修复

### 问题定位
- **文件**: `backend/services/workflow_runtime/visual_audio_assets.py`
- **问题**: 使用全局变量 `runtime_config.TOS_ASSETS_PREFIX`，该变量在服务启动时根据默认项目名 `default` 初始化
- **影响**: 所有项目都使用相同的路径 `manju/default/assets`，导致多项目并行时资产冲突

### 修复内容
将7处使用 `runtime_config.TOS_ASSETS_PREFIX` 的代码改为使用 `runtime_config.get_project_prefixes(runtime_config.PROJECT_NAME)["TOS_ASSETS_PREFIX"]`：

1. `download_assets_from_tos` 函数
2. `load_upload_jsonl` 函数
3. `upload_jsonl_to_assets` 函数
4. `character_prompts` 生成部分
5. `location_images` 生成部分
6. `fenjing_prompts` 下载部分
7. `fenjing_prompts` 上传部分

### 修复验证
- ✅ 语法检查通过
- ✅ 服务重启成功
- ✅ 新项目创建成功

---

## 第二轮测试（修复后）

### 新创建的项目
- **Agent A 项目**: `e2e_fix_a_20260217_210106`
- **Agent B 项目**: `e2e_fix_b_20260217_210106`

服务已重启并应用修复，等待执行步骤1-4验证修复是否生效。

**预期TOS路径**:
- Agent A: `manju/e2e_fix_a_20260217_210106/assets/`
- Agent B: `manju/e2e_fix_b_20260217_210106/assets/`

---

## 关键发现

### 1. 多项目并行支持
- 步骤1-3（auto_storyboard）支持多项目并行执行
- 步骤4（visual_audio_assets）修复前存在TOS路径冲突问题

### 2. 修复验证方法
通过检查错误日志中的 `request_url` 可以确认修复是否生效：
- **修复前**: `https://fzruse.tos-cn-beijing.volces.com/manju/default/assets/characters.jsonl`
- **修复后**: `https://fzruse.tos-cn-beijing.volces.com/manju/{project_name}/assets/characters.jsonl`

### 3. 服务重启要求
代码修复后必须重启服务才能生效，因为Python模块在导入时缓存了全局变量。

---

## 建议

1. **代码审查**: 检查其他 workflow runtime 文件，确保没有类似的全局变量使用问题
2. **自动化测试**: 添加多项目并行的自动化测试用例
3. **文档更新**: 更新开发文档，明确说明多项目并行时的TOS路径规则

---

## 修复提交

**修改文件**: `backend/services/workflow_runtime/visual_audio_assets.py`  
**修改行数**: 7处  
**修改类型**: Bug修复（多项目并行支持）

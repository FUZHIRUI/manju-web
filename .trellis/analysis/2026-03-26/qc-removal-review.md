# QC（质量检查）代码移除 Review 报告

> 生成时间：2026-03-26
> 分析工具：python-abcoder (AST) + Grep

## 1. QC 代码分布总览

| 层级 | 文件 | QC 引用数 | 影响程度 |
|------|------|-----------|----------|
| **Runtime** | `backend/services/workflow_runtime/visual_audio_assets.py` | ~100+ 行 | **重度** - 角色图像 QC 主逻辑 |
| **Runtime** | `backend/services/workflow_runtime/fenjing.py` | ~40+ 行 | **中度** - 分镜 QC 字段+返回值 |
| **Runtime** | `backend/services/workflow_runtime/provider_runtime.py` | 2 个函数 | **中度** - QC API 调用层 |
| **Config** | `backend/services/workflow_runtime/config.py` | 4 行 | 轻度 - QC 配置字段 |
| **Config** | `backend/services/workflow_runtime/runtime_config.py` | ~10 行 | 轻度 - QC 全局配置变量 |
| **Config** | `backend/services/config_defaults.py` | 2 行 | 轻度 - QC 默认值 |
| **Repo** | `backend/repositories/asset_repo.py` | ~50+ 行 | **重度** - QC 数据读取/解析 |
| **Service** | `backend/services/asset_stats_service.py` | 1 行 | 轻度 - QC 统计判断 |
| **Service** | `backend/services/job_service.py` | 1 行 | 轻度 - QC 失败构建 |
| **Frontend** | `frontend/app.js` | ~10 行 | 中度 - QC 失败 UI 展示 |
| **Frontend** | `frontend/style.css` | ~20 行 | 轻度 - QC CSS 样式 |
| **Prompt** | `prompt/character_build_qc.txt` | 整个文件 | 可删除 |
| **Prompt** | `prompt/character_cloth_qc.txt` | 整个文件 | 可删除 |
| **Prompt** | `prompt/fenjing_qc.txt` | 整个文件 | 可删除 |
| **Prompt** | `prompt/fengjing_qc_multirole.txt` | 整个文件 | 可删除 |
| **Test** | `backend/tests/test_fenjing_refactor.py` | 2 行 | 轻度 |

---

## 2. QC 代码详细分析

### 2.1 `visual_audio_assets.py` — 角色图像 QC 主逻辑（最重量级）

**核心 QC 流程 1：角色服装 QC（L875-1084）**
- `process_single_image_with_qc()` (内嵌闭包) — 对生成的角色服装图进行 QC 检查，失败则重试
- 读取 `character_cloth_qc.txt` prompt
- 调用 `qc_image_async()` 进行图像质量检查
- 多次重试机制（生成→QC→失败→重新生成→再 QC）
- 输出 `qc_passed`, `qc_result` 字段

**核心 QC 流程 2：角色构建 QC（L1910-2407）**
- 读取 `character_build_qc.txt` prompt
- `resolve_character_prompts_paths()` 中包含 `character_qc_prompts_path`
- 完整的 QC 循环：生成图像→QC检查→解析结果→通过/重试
- 写入 `character_qc_results.jsonl` 结果文件
- `resolve_qc_pass()` 辅助函数解析 QC 结果
- 统计日志：`Character QC Completed. Expected: X, Passed: Y`

### 2.2 `fenjing.py` — 分镜 QC

- `process_single_fenjing_with_qc()` (L424) — 名称包含 QC 但实际 QC 逻辑已简化
- 所有返回 dict 都包含 `"qc_passed": None` 字段（~15 处）
- 返回值中包含 `fenjing_qc_csv`, `fenjing_qc_csvs` 空列表/字典（~8 处）

### 2.3 `provider_runtime.py` — QC API 调用

- `qc_image_async()` (L912) — 异步包装
- `qc_image()` (L922) — 实际 QC 图像检查 API 调用

### 2.4 `asset_repo.py` — QC 数据层

- `_load_character_qc_map()` (L975) — 从 `character_qc_results.jsonl` 加载 QC 结果
- `_extract_qc_pass()` (L1001) — 解析 QC 通过状态
- `_extract_qc_reason()` (L1009) — 提取 QC 失败原因
- `build_partial_failures_from_qc()` (L912) — 构建 QC 失败列表
- 多处读取 `qc_pass`, `qc_attempts`, `qc_reason`, `qc_limit` 字段

### 2.5 配置层

**`config.py`**: `qc_thinking`, `qc_reasoning_effort` 字段
**`runtime_config.py`**: `QC_THINKING`, `QC_REASONING_EFFORT`, `FENJING_QC_THINKING`, `FENJING_QC_REASONING_EFFORT`
**`config_defaults.py`**: `DEFAULT_QC_THINKING`, `DEFAULT_QC_REASONING_EFFORT`

### 2.6 Frontend

**`app.js`**:
- L1954: errorPatterns 包含 "QC"
- L3970-4011: QC 失败卡片展示逻辑（红框、"QC失败"徽章、失败原因标签）

**`style.css`**:
- `.qc-failed-asset`, `.qc-failed-badge`, `.qc-reason-tag` 样式

### 2.7 Prompt 模板文件（可直接删除）

- `prompt/character_build_qc.txt` — 角色构建质检 prompt
- `prompt/character_cloth_qc.txt` — 角色服装质检 prompt
- `prompt/fenjing_qc.txt` — 分镜质检 prompt
- `prompt/fengjing_qc_multirole.txt` — 多角色分镜质检 prompt

---

## 3. 移除影响分析

### 高风险区域
1. **`visual_audio_assets.py`** — QC 逻辑深度嵌入角色图像生成流程，移除需要重构生成→QC→重试循环为单纯的生成流程
2. **`asset_repo.py`** — QC 数据读取贯穿资产展示逻辑，需确保移除后资产列表仍能正常返回

### 中风险区域
3. **`fenjing.py`** — 返回值结构中包含 `qc_passed`/`fenjing_qc_csv` 字段，前端或其他消费者可能依赖
4. **`provider_runtime.py`** — `qc_image_async`/`qc_image` 被 visual_audio_assets 调用

### 低风险区域
5. 配置变量、常量、CSS 样式 — 删除即可，无逻辑依赖

---

## 4. 建议移除顺序

1. **删除 Prompt 文件**（4个 .txt）
2. **删除 provider_runtime.py 中的 QC 函数**（`qc_image_async`, `qc_image`）
3. **重构 visual_audio_assets.py** — 将 `process_single_image_with_qc` 简化为纯生成（去掉 QC 循环），移除 `character_qc_results.jsonl` 写入
4. **清理 fenjing.py** — 移除返回值中的 `qc_passed`, `fenjing_qc_csv`, `fenjing_qc_csvs` 字段
5. **清理 asset_repo.py** — 删除 `_load_character_qc_map`, `_extract_qc_pass`, `_extract_qc_reason`, `build_partial_failures_from_qc`，清理资产列表中的 QC 字段
6. **清理配置** — config.py, runtime_config.py, config_defaults.py 中的 QC 变量
7. **清理 job_service.py, asset_stats_service.py** 中的 QC 引用
8. **清理 Frontend** — app.js 中的 QC 展示逻辑，style.css 中的 QC 样式
9. **清理测试** — test_fenjing_refactor.py 中的 QC 引用

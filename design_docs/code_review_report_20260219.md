# Manju Web 项目代码审查报告（2026-02-19）

## 概览
- 审查范围：`backend/`、`frontend/`、`skills/`、`design_docs/`、`requirments_doc/`
- 技术栈：Python 3.9（后端，ThreadingHTTPServer）、原生 JS/CSS（前端）
- 结论：有条件通过。核心架构清晰（按项目隔离输出与状态、统一限流与存储），但存在可移除冗余、并发持久化隐患与前后端状态融合逻辑分散。

## 关键结论
- 状态持久化安全：`flow_state.json` 使用临时文件+原子替换写入，线程安全良好（`backend/repositories/status_repo.py:26`）。
- 作业快照持久化存在并发隐患：`jobs.jsonl` 采用覆盖式写入（`backend/server.py:86–109`），多线程并发更新可能丢写。
- 多项目并行具备路径与前缀隔离：项目输出与TOS前缀按项目名生成（`backend/repositories/project_repo.py:23`，`backend/services/workflow_runtime/runtime_config.py:474`）。模型与阶段限流共享全局配额（`backend/services/throttle_service.py:79–136`）。
- 分镜生成与上传状态融合：前端对卡片动效与鱼骨图使用两处融合逻辑，易漂移（`frontend/app.js:2711`、`frontend/app.js:2828`）。

## 可移除的冗余/重复
- 未使用导入与变量（示例）：
  - `backend/services/workflow_runtime/fenjing.py:1` 的 `os`
  - `backend/services/workflow_runtime/fenjing.py:7` 的 `Set`
  - `backend/services/workflow_runtime/fenjing.py:11` 的 `qc_image_async`
- 重复工具函数实现：
  - `safe_project_name` 重复于 `backend/server.py:197` 与 `backend/repositories/project_repo.py:14`
  - `project_base_dir` 重复于 `backend/server.py:206` 与 `backend/repositories/project_repo.py:23`
  - `safe_read_jsonl` 重复于 `backend/server.py:252` 与 `backend/repositories/project_repo.py:73`
- 备份/历史文件（如存在）：`backend/services/workflow_runtime/visual_audio_assets.py.bak:1`（建议移除避免歧义）

## 工作流中实际未使用的方法（可考虑移除或保留为未来扩展）
- `backend/services/status_service.py:292` 的 `reset_visual_audio_steps_except(project, keep_steps)`
  - 用途：重置除保留步骤外的视觉音频步骤
  - 现状：未在工作流调用处使用，仅在测试文件中引用
- `backend/services/status_service.py:719` 的 `check_fenjing_images_exist(project)`
  - 用途：检测分镜图片是否存在
  - 现状：仅被同文件的 `mark_fenjing_generate_partial` 调用；该方法未在工作流入口处使用
- `backend/services/status_service.py:736` 的 `mark_fenjing_generate_partial(project)`
  - 用途：根据是否存在图片将分镜生成标记为部分完成
  - 现状：未在工作流中使用（无入口调用）
- `backend/services/throttle_service.py:119` 的 `get_stage_limiter(stage_key)`
  - 用途：读取阶段并发限制器
  - 现状：工作流统一通过 `acquire_stage_limit` 获取并发控制；该读取方法未被实际使用

## 多项目并行隐患与建议
- 作业索引非原子写：
  - 问题：`write_jobs_to_disk` 覆盖式写入（`backend/server.py:86–93`）与并发快照更新存在竞态。
  - 建议：仿照 `write_flow_state` 实现“临时文件+原子替换”，参考 `backend/repositories/status_repo.py:31–33`。
- 全局限流与鉴权共享：
  - 模型/TOS鉴权使用全局变量（`backend/services/workflow_runtime/runtime_config.py:240–299, 392–459`），阶段/模型限流共享（`backend/services/throttle_service.py:99–113`）。
  - 风险：大项目压小项目资源；若需项目级QoS，建议在限流器键上增加项目命名空间（如 `seedream_4_5@<project>`）并允许项目级覆盖。

## 修复后可能的功能重叠
- 分镜引用选择策略分散：本地/服务端两处实现 outfit→参考图映射与TOS兜底。
  - 位置示例：`backend/services/workflow_runtime/fenjing.py:1420–1474` 与 `backend/services/workflow_runtime/fenjing.py:734–771`
  - 建议：抽象 `select_reference_images(item, storyboards, cloth_changed_map, char_map, project_name)`，统一复用，降低维护风险。
- 前端状态融合分散：
  - 鱼骨图状态合并：`frontend/app.js:2711–2743`（将 `fenjing_upload` 步骤并入 `fenjing_generate`）
  - 卡片动效融合：`frontend/app.js:2828–2840`（上传运行时，令 `fenjing_generate` 卡片进入 `running`）
  - 建议：抽象 `resolveEffectiveFlowStatus(flow)` 并在两处复用，确保卡片动效与鱼骨状态来源一致。

## 已验证的改动点（示例）
- 上传分镜状态事件映射：`backend/services/status_service.py:605–621` 增加对 `fenjing_upload_start`/`fenjing_upload_complete` 的处理，上传运行/完成状态可正确落盘。
- 前端动效：
  - 卡片呼吸动效：`frontend/style.css:135–140`（基于 `job-item[data-status="running"]`）
  - 上传按钮呼吸动效：`frontend/style.css:1618–1629` 与 `frontend/app.js:825–847`
  - 鱼骨状态合并显示：`frontend/app.js:2711–2743`

## 改进计划（优先级从高到低）
- 修复 `jobs.jsonl` 持久化的原子写：引入临时文件写入+原子替换。
- 统一后端公共工具：移除 `server.py` 中重复的 `safe_project_name/project_base_dir/safe_read_jsonl`，改为仓库层导入。
- 抽象分镜引用选择策略：新增一个函数统一处理引用选择与兜底逻辑。
- 收敛前端状态融合：实现 `resolveEffectiveFlowStatus(flow)` 并复用于卡片渲染与鱼骨图更新。
- 清理未使用的导入与变量，移除历史备份文件。

## 验证建议
- 并发写测试：模拟多线程同时更新同一项目的 `jobs.jsonl`，验证原子写后快照不丢失（参考 `backend/tests/test_flow_state_persistence.py:109–133` 的模式）。
- 前端一体化验证：在 batch 页面同时触发分镜生成与上传，检查卡片动效与鱼骨状态一致性（卡片呼吸：`frontend/style.css:135`；鱼骨 running/complete 状态）。
- 多项目压力测试：同时运行多项目资产生成与上传，观察限流器是否满足QoS预期；若需要，验证项目级限流命名空间的效果。

## 参考代码位置
- 状态持久化：`backend/repositories/status_repo.py:6, 12, 26`
- 作业快照持久化：`backend/server.py:86–109`
- 项目目录：`backend/repositories/project_repo.py:23–48`
- TOS前缀（按项目）：`backend/services/workflow_runtime/runtime_config.py:474`
- 分镜生成事件：`backend/services/workflow_runtime/fenjing.py:1428–1474`
- 前端鱼骨图更新：`frontend/app.js:2711–2799`
- 卡片渲染与动效：`frontend/app.js:2814–2864`，`frontend/style.css:135–140`

---
（本报告不包含鉴权文档与密钥信息，符合安全要求。）

# 分镜图生成步骤拆分实现计划

## 任务列表

### Phase 1: 后端 - 状态管理

- [x] **Task 1.1**: 修改 `status_service.py` - 新增 flow 定义
  - 在 `_FLOW_STEPS` 中添加 `fenjing_generate` 和 `fenjing_upload`
  - 在 `_PARTIAL_STEPS` 中添加 `fenjing_generate: ["generate_images"]`
  - 在 `_resolve_step` 函数中添加新 flow 的事件解析逻辑

- [x] **Task 1.2**: 修改 `status_service.py` - 新增状态更新函数
  - 添加 `mark_fenjing_generate_partial()` 函数
  - 添加 `check_fenjing_images_exist()` 函数

### Phase 2: 后端 - 工作流拆分

- [x] **Task 2.1**: 修改 `fenjing.py` - 拆分生成函数
  - 新增 `run_fenjing_generate_workflow()` 函数
  - 生成分镜图到本地目录，不上传
  - 发出独立事件：`fenjing_generate_start`, `fenjing_generate_complete` 等

- [x] **Task 2.2**: 修改 `fenjing.py` - 拆分上传函数
  - 新增 `run_fenjing_upload_workflow()` 函数
  - 读取本地分镜图，上传到 TOS
  - 使用 `throttle_service` 限流
  - 发出独立事件：`fenjing_upload_start`, `fenjing_upload_complete` 等

- [x] **Task 2.3**: 修改 `fenjing.py` - 保留原流程兼容
  - 修改 `run_fenjing_workflow_multi()` 内部调用拆分后的函数

### Phase 3: 后端 - API 端点

- [x] **Task 3.1**: 修改 `job_repo.py` - 新增 Job 类型映射
  - 添加 `run_fenjing_generate` 和 `run_fenjing_upload` 映射

- [x] **Task 3.2**: 修改 `server.py` - 新增 API 端点
  - 添加 `POST /api/projects/{project}/run/fenjing_generate` 端点
  - 添加 `POST /api/projects/{project}/run/fenjing_upload` 端点
  - 上传前检查生成状态是否为 `completed` 或 `partial_completed`

### Phase 4: 后端 - 限流配置

- [x] **Task 4.1**: 修改 `throttle_service.py` 或配置文件
  - 添加 `fenjing_upload` 限流配置：`qps: 5, concurrency: 10`

### Phase 5: 前端 - 按钮与状态（保持现有交互逻辑）

- [x] **Task 5.1**: 修改 `app.js` - 新增 FLOW_TREE_CONFIG
  - 添加 `fenjing_generate` 配置（参考现有 `fenjing` 配置）
  - 添加 `fenjing_upload` 配置

- [x] **Task 5.2**: 修改 `app.js` - 修改 `appendFenjingPhaseButtons` 函数
  - **保持现有交互逻辑结构**
  - 参考 `appendVisualAudioPhaseButtons` 的实现
  - 将原来的"执行"按钮拆分为两个按钮：
    - "第一步：分镜图生成"
    - "第二步：上传"（生成完成后才显示）
  - 添加 `flow_status` 状态检查，completed 状态时禁用按钮

- [x] **Task 5.3**: 修改 `app.js` - 修改 `submitFlow` 函数
  - 添加 `fenjing_generate` 和 `fenjing_upload` 到 pending 流程支持

- [x] **Task 5.4**: 修改 `app.js` - 新增 `executeFlowFull` 支持
  - 添加 `fenjing_generate` 和 `fenjing_upload` 的执行支持

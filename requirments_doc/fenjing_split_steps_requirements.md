# 分镜图生成步骤拆分需求分析

## 1. 需求背景

当前分镜图生成流程将"图片生成"和"上传"耦合在一起，用户无法在生成后检查图片质量再决定是否上传。需要拆分为两个独立的步骤。

## 2. EARS 分析

### 2.1 事件 (Event)
- 用户点击"分镜图生成"按钮
- 分镜图生成完成
- 用户点击"上传"按钮
- 上传完成

### 2.2 角色 (Actor)
- 用户：操作前端界面
- 后端服务：执行生成和上传任务
- TOS：云存储服务

### 2.3 请求 (Request)
- 生成分镜图：下载资产 → 生成分镜图到本地目录
- 上传分镜图：读取本地分镜图 → 上传到 TOS（限制 QPS）

### 2.4 范围 (Scope)
- 分镜图生成流程
- flow_status 状态管理
- 前端按钮显示逻辑

## 3. 功能需求

### 3.1 分镜图生成步骤 (Step 1: Generate)
1. 下载资产（characters.jsonl, locations.jsonl 等）
2. 生成分镜图到本地目录
3. 发出独立的完成事件：`fenjing_generate_complete`
4. 更新 flow_status：`fenjing.generate = "completed"`

### 3.2 上传步骤 (Step 2: Upload)
1. 读取本地已生成的分镜图
2. 限制上传 QPS（避免触发 TOS 限流）
3. 发出独立的上传事件：`fenjing_upload_start`, `fenjing_upload_progress`, `fenjing_upload_complete`
4. 更新 flow_status：`fenjing.upload = "completed"`

### 3.3 状态管理
- 两个步骤的状态独立互不影响
- 生成完成后，上传状态为 `waiting`
- 上传可以独立重试，不影响生成状态

## 4. 非功能需求

### 4.1 上传 QPS 限制
- 上传请求 QPS 限制为可配置值（默认 5 QPS）
- 使用令牌桶或信号量控制并发

### 4.2 事件解耦
- 生成事件：`fenjing_generate_*`
- 上传事件：`fenjing_upload_*`
- 两类事件独立，不相互依赖

### 4.3 状态独立性
```json
{
  "fenjing": {
    "status": "partial_completed",
    "steps": {
      "generate": "completed",
      "upload": "waiting"
    }
  }
}
```

## 5. 影响评估

### 5.1 接口变更
- 新增 API：`POST /api/projects/{project}/run/fenjing_generate`
- 新增 API：`POST /api/projects/{project}/run/fenjing_upload`
- 保留原 API：`POST /api/projects/{project}/run/fenjing`（兼容旧流程）

### 5.2 前端适配
- 按钮显示逻辑变更
- flow 配置变更

### 5.3 数据迁移
- 无需数据迁移，新增状态字段向后兼容

## 6. 约束条件

### 6.1 线程安全
- 多项目并行场景下，状态更新需要线程安全
- 上传 QPS 限制需要跨项目共享

### 6.2 兼容性
- 保留原有 `run_fenjing` API，支持一键执行完整流程
- 新增拆分 API，支持分步执行

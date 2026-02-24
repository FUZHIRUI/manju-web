# 需求文档：Fenjing Flow 统一重构

## 1. 概述

### 1.1 背景
当前 `fenjing` 相关的 flow 存在三个独立实体：`fenjing`、`fenjing_generate`、`fenjing_upload`，导致状态管理混乱、代码重复、维护困难。

### 1.2 目标
将 `fenjing_generate` 和 `fenjing_upload` 统一收编到 `fenjing` flow 中，简化状态管理，与 `visual_audio_assets` 的设计模式保持一致。

## 2. EARS 需求分析

### 2.1 功能需求

#### FR-001: Flow 统一收编
- **Event**: 当用户执行分镜相关操作时
- **Actor**: 系统
- **Request**: 将 `fenjing_generate` 和 `fenjing_upload` 的步骤合并到 `fenjing` flow
- **Scope**: 后端状态管理、工作流服务、API Handler

**详细说明**:
- `fenjing` flow 统一包含步骤：`["download_assets", "generate_images", "upload_assets"]`
- 移除 `fenjing_generate` 和 `fenjing_upload` 作为独立 flow
- 现有状态数据需迁移：`fenjing_generate`/`fenjing_upload` 的状态合并到 `fenjing`

#### FR-002: 前端 Job-Item 卡片兼容
- **Event**: 当前端渲染分镜相关的 job-item 卡片时
- **Actor**: 前端用户
- **Request**: 卡片正常显示分镜生成和上传按钮，状态正确反映
- **Scope**: 前端 `app.js`、`index.html`

**详细说明**:
- 分镜生成按钮：触发 `fenjing` flow 的 `generate_images` 步骤
- 分镜上传按钮：触发 `fenjing` flow 的 `upload_assets` 步骤
- 卡片状态：基于 `fenjing` flow 的整体状态和步骤状态渲染

#### FR-003: 多项目线程安全
- **Event**: 当多个项目并发执行分镜操作时
- **Actor**: 系统
- **Request**: 确保每个项目的状态操作线程安全，互不干扰
- **Scope**: 后端 `status_service.py`

**详细说明**:
- 使用项目级别的锁机制（已实现 `_get_project_lock`）
- 验证重构后的代码不破坏现有锁机制
- 确保状态迁移过程的原子性

### 2.2 非功能需求

#### NFR-001: 向后兼容
- 现有 API 接口需保持兼容，前端无需大规模改动
- 旧的状态文件格式需能自动迁移

#### NFR-002: 数据迁移
- 现有项目的 `flow_state.json` 需自动迁移到新格式
- 迁移过程不能丢失已有状态

#### NFR-003: 测试覆盖
- 需补充单元测试验证重构后的状态计算逻辑
- 需验证前端按钮点击后的完整流程

## 3. 影响评估

### 3.1 后端影响

| 文件 | 变更类型 | 影响描述 |
|------|----------|----------|
| `status_service.py` | 修改 | 移除 `fenjing_generate`/`fenjing_upload` 定义，更新事件处理 |
| `workflow_service.py` | 修改 | 合并 `run_fenjing_generate`/`run_fenjing_upload` 到 `run_fenjing` |
| `job_handler.py` | 修改 | 更新 workflow 路由逻辑 |
| `project_handler.py` | 修改 | 更新 flow 白名单 |
| `asset_repo.py` | 修改 | 更新产物路径逻辑 |
| `job_repo.py` | 修改 | 更新 job 类型映射 |

### 3.2 前端影响

| 文件 | 变更类型 | 影响描述 |
|------|----------|----------|
| `app.js` | 修改 | 更新 flow 名称引用，约 40+ 处 |
| `index.html` | 修改 | 更新按钮 data-flow 属性 |

### 3.3 数据迁移

| 数据 | 迁移策略 |
|------|----------|
| `flow_state.json` | 启动时自动迁移，合并旧 flow 状态到新 flow |

## 4. 验收标准

### 4.1 功能验收
- [ ] `fenjing` flow 包含三个步骤：`download_assets`, `generate_images`, `upload_assets`
- [ ] `fenjing_generate` 和 `fenjing_upload` 不再作为独立 flow 存在
- [ ] 前端分镜生成按钮可正常点击并执行
- [ ] 前端分镜上传按钮可正常点击并执行
- [ ] job-item 卡片状态正确显示

### 4.2 非功能验收
- [ ] 多项目并发执行无竞态条件
- [ ] 现有项目状态自动迁移，无数据丢失
- [ ] 单元测试全部通过

## 5. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 状态迁移失败 | 低 | 高 | 保留迁移前备份，提供回滚脚本 |
| 前端兼容性问题 | 中 | 中 | 保持 API 接口兼容，前端渐进式更新 |
| 并发竞态 | 低 | 高 | 使用项目级锁，充分测试 |

## 6. 附录

### 6.1 当前 Flow 结构
```python
_FLOW_STEPS = {
    "fenjing": ["download_assets", "generate_images", "upload_assets"],
    "fenjing_generate": ["download_assets", "generate_images"],
    "fenjing_upload": ["upload_fenjing_images"],
}
```

### 6.2 目标 Flow 结构
```python
_FLOW_STEPS = {
    "fenjing": ["download_assets", "generate_images", "upload_assets"],
}
```

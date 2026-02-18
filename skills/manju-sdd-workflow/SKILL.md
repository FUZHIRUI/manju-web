---
name: manju-sdd-workflow
description: 强制执行 SDD (Software Design Description) 开发流程。当用户提出新的开发需求、功能变更或要求遵循 SDD 规范时使用。包含现状分析、需求分析、系统设计、实现计划、编码及验证的全流程管理。
---

# Skill: ManjuSDDWorkflow

## Description
本 Skill 旨在规范 `/Users/bytedance/Desktop/常见python/manju_web` 项目的开发流程，解决智能体执行顺序遵循度不足的问题。
它强制执行“现状调研 -> 需求分析 -> 系统设计 -> 实现计划 -> 编码验证”的严格顺序流程。

## Workflow

### Phase 0: 现状调研 (Pre-Analysis)
**在回答用户需求之前，必须先执行此步骤。**
1.  **代码审查**: 检查项目当前的前后端实现，确认与用户需求相关的现有功能。
    *   使用 `SearchCodebase` 或 `Grep` 查找相关代码。
2.  **事实确认**: 验证当前实现的实际行为。
    *   **日志分析**: 检查 `manju_web/backend/logs/` 下的最近日志。
    *   **数据检查**: 检查 `manju_web/backend/data` 或相关 JSONL 文件中的数据结构。
    *   **Mock 验证**: 如果必要，编写简单的脚本验证关键函数的返回值。
3.  **输出**: 向用户汇报当前项目的实现现状，确认是否与用户描述一致。

### Phase 1: 需求分析 (Requirement Analysis)
1.  **沟通与梳理**: 与用户对话，澄清需求细节。
2.  **EARS 分析**: 使用 EARS 语法 (Event, Actor, Request, Scope) 梳理功能点。
3.  **文档生成**: 生成 `{requirement_name}_requirements.md`，保存至 `manju_web/requirments_doc/`。
4.  **影响评估**: 分析本次变更对现有系统的影响（接口变更、数据迁移、前端适配等）。
5.  **暂停点 (STOP)**:
    *   输出文档内容。
    *   **必须询问**: “需求分析已完成，内容是否准确？如果确认，请回复‘确认，进入系统设计阶段’。”
    *   **等待用户确认**。若用户修改，重新生成并再次确认。

### Phase 2: 系统设计 (System Design)
**前提**: 用户已确认 Phase 1 的文档。
1.  **技术方案**: 基于 `requirements.md` 进行技术选型、组件设计、接口定义和数据模型设计。
2.  **文档生成**: 生成 `{requirement_name}_design.md`，保存至 `manju_web/requirments_doc/`。
3.  **暂停点 (STOP)**:
    *   输出文档内容。
    *   **必须询问**: “系统设计已完成，技术方案是否合理？如果确认，请回复‘确认，进入实现计划阶段’。”
    *   **等待用户确认**。若用户修改，重新生成并再次确认。

### Phase 3: 实现计划 (Implementation Planning)
**前提**: 用户已确认 Phase 2 的文档。
1.  **任务拆解**: 将 `design.md` 分解为微小的、可执行的编码任务。
2.  **文档生成**: 生成 `{requirement_name}_tasks.md`，保存至 `manju_web/requirments_doc/`。
    *   格式必须为 Markdown 任务列表 (`- [ ] Task Description`)。
3.  **暂停点 (STOP)**:
    *   输出文档内容。
    *   **必须询问**: “实现计划已拆解完毕，任务列表是否清晰？如果确认，可以开始执行编码。”
    *   **等待用户确认**。若用户修改，重新生成并再次确认。

### Phase 4: 编码与验证 (Coding & Verification)
**前提**: 用户已确认 Phase 3 的任务列表。
1.  **执行编码**: 按照 `tasks.md` 顺序执行代码修改。
    *   每完成一个任务，勾选 `tasks.md` 中的对应项。
2.  **静态检查**: 代码修改完成后，运行静态检查（如 `pylint`, `mypy` 或项目自带的检查脚本）。
3.  **验证**:
    *   **调用验证 Skill**: 编码完成后，**必须立即调用 `manju-verifier` skill**。
    *   使用 `manju-verifier` 生成或更新测试用例。
    *   执行测试并修复所有发现的 Bug。

## Constraints
- **禁止跳跃**: 严禁在未获得用户对上一阶段文档确认的情况下进入下一阶段。
- **文档路径**: 所有文档必须保存在 `/Users/bytedance/Desktop/常见python/manju_web/requirments_doc/`。
- **循环禁止**: 当某一阶段的 MD 生成后，按照顺序图继续向下一步骤执行，禁止陷入无意义的循环讨论，除非用户明确提出修改意见。
- **验证强制**: 编码结束后必须进行测试验证，不可直接交付未验证的代码。

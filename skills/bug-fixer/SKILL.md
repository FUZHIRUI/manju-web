---
name: bug-fixer
description: 项目Bug排查与修复技能。通过日志分析、代码审查、执行验证等多种方式，系统性地排查和修复项目中的bug问题。适用于用户报告bug、系统出现异常、需要诊断问题原因等场景。
---

# Skill: Bug Fixer

## Description

针对 `/Users/bytedance/Desktop/常见python/manju_web` 项目的系统性Bug排查与修复技能。

主要功能：
1. **状态机追踪**：通过拍摄状态快照，追踪状态机在Step执行前后的变化
2. **产物对比**：监控和对比产物文件（artifacts）的生成和变化
3. **日志分析**：自动扫描和分析项目日志文件，识别错误模式和异常
4. **代码审查**：基于问题描述进行针对性的代码搜索和分析
5. **问题诊断**：通过前后状态对比、日志分析、代码审查来定位问题根因

## Workflow

### Step 1: 问题理解与信息收集

在开始排查前，必须先完成此步骤。

1. **问题描述确认**：
   - 询问用户详细的bug描述：发生了什么、预期行为、实际行为
   - 确认复现步骤、触发条件、影响范围
   - 收集相关的错误信息、截图、日志片段

2. **环境检查**：
   - 检查后端服务运行状态（terminal 15）
   - 确认项目目录结构和关键文件位置
   - 检查最近的代码变更记录

3. **快速扫描**：
   - 检查 `backend/logs/` 目录下的最新日志
   - 查看终端输出是否有错误信息
   - 检查前端控制台是否有JavaScript错误

### Step 2: 日志深度分析

1. **日志文件定位**：
   - 使用 `scripts/analyze_logs.py` 扫描所有日志文件
   - 优先查看最新的日志文件（按修改时间排序）
   - 重点关注 ERROR、WARNING、EXCEPTION 级别日志

2. **错误模式识别**：
   - 搜索常见错误关键词：Traceback、Error、Exception、Failed
   - 分析堆栈跟踪信息，定位问题发生的代码位置
   - 识别重复出现的错误模式

3. **上下文分析**：
   - 查看错误发生前后的日志记录
   - 分析请求/响应流程
   - 关联相关的业务操作

### Step 3: 代码审查与问题定位

1. **代码搜索**：
   - 使用 `SearchCodebase` 或 `Grep` 工具搜索相关代码
   - 基于日志中的文件名、函数名、错误信息定位代码
   - 查看相关的Handler、Service、Repository层代码

2. **数据流分析**：
   - 追踪数据从输入到输出的完整流程
   - 检查数据验证、转换逻辑
   - 识别可能的边界条件和空值处理问题

3. **依赖检查**：
   - 检查相关函数的调用关系
   - 验证外部服务调用（API、数据库等）
   - 确认配置项是否正确

### Step 4: 状态监控与前后对比

**核心原则**：不硬编码特定操作步骤，而是通过状态机变化、Step执行前后的状态和产物变化来诊断问题。

1. **执行前状态快照**：
   - 使用 `scripts/reproduce_bug.py --snapshot` 拍摄操作前的状态快照
   - 记录当前的Job状态、项目状态、产物文件列表
   - 标记为 "BEFORE" 快照

2. **执行用户操作**：
   - 让用户在前端执行触发问题的操作
   - 或者监控特定的Job执行：`scripts/reproduce_bug.py --monitor --job-id <job_id>`

3. **执行后状态快照**：
   - 操作完成后再次拍摄状态快照
   - 标记为 "AFTER" 快照

4. **状态对比分析**：
   - 使用脚本自动对比前后快照的差异
   - 重点关注：
     - Job状态的变化（status、phases等）
     - 产物文件的新增、修改、删除
     - 项目状态的变更
   - 识别异常的状态跳转或缺失的产物

5. **根因定位**：
   - 结合日志分析和状态对比结果
   - 追踪数据流在Step执行过程中的变化
   - 定位导致问题的具体环节

### Step 5: 修复实施与验证

1. **修复方案确定**：
   - 基于分析结果提出修复方案
   - 评估修复方案的影响范围
   - 与用户确认修复方案

2. **代码修改**：
   - 按照修复方案修改代码
   - 遵循项目代码风格和规范
   - 添加必要的注释和测试

3. **完整验证**：
   - 运行相关测试用例
   - 执行端到端验证
   - 检查日志确认无新错误

4. **结果总结**：
   - 总结问题根因
   - 说明修复方案
   - 提供预防建议

## Key Tools & Resources

### Scripts
- `scripts/analyze_logs.py` - 日志分析脚本，自动扫描和分析日志文件
- `scripts/reproduce_bug.py` - **状态监控与诊断工具**：拍摄状态快照、监控Job执行、对比前后状态变化、追踪产物文件
- `scripts/check_code_quality.py` - 代码质量检查脚本

### References
- `references/common_issues.md` - 常见问题排查指南
- `references/debug_patterns.md` - 调试模式和技巧

## Constraints

- **必须优先分析日志**：在进行代码修改前，必须先完成日志分析
- **必须复现问题**：修复前必须能够稳定复现问题（除非是偶发问题）
- **验证必须完整**：修复后必须进行完整的验证，包括相关功能测试
- **遵循项目规范**：代码修改必须遵循项目现有的代码风格和架构模式
- **不破坏现有功能**：修复bug时不能引入新的问题或破坏现有功能

## Common Scenarios

### 场景1: 前端报错
1. 打开浏览器开发者工具查看Console错误
2. 检查Network标签查看API请求/响应
3. 定位前端代码中的问题位置
4. 检查后端对应接口是否正常

### 场景2: 后端报错
1. 查看 `backend/logs/` 下的最新日志
2. 分析堆栈跟踪信息
3. 定位问题代码位置
4. 检查相关配置和依赖

### 场景3: 状态异常
1. 检查工作流状态流转逻辑
2. 验证状态更新的触发条件
3. 检查前端状态同步机制
4. 确认数据库/存储中的状态值

### 场景4: 功能不工作
1. 确认用户操作步骤
2. 检查API调用是否正常
3. 验证业务逻辑执行
4. 排查数据流程问题

## 状态监控工具使用指南

### `reproduce_bug.py` 常用命令

```bash
# 查看项目列表
python scripts/reproduce_bug.py --list-projects

# 查看当前完整状态
python scripts/reproduce_bug.py --project-id <project_id> --current-state

# 拍摄单次状态快照
python scripts/reproduce_bug.py --project-id <project_id> --snapshot

# 监控Job执行（自动拍摄快照并对比）
python scripts/reproduce_bug.py --project-id <project_id> --job-id <job_id> --monitor

# 导出快照到文件
python scripts/reproduce_bug.py --project-id <project_id> --snapshot --export debug_snapshot.json
```

### 诊断流程示例

1. **用户报告问题**："换装按钮点击后，cloth_images状态一直是running"
2. **拍摄操作前快照**：`--snapshot`
3. **让用户点击按钮**：在前端执行操作
4. **拍摄操作后快照**：`--snapshot`
5. **对比分析**：查看状态变化、产物生成情况
6. **结合日志**：使用 `analyze_logs.py` 查看相关日志
7. **定位根因**：找出状态未更新的原因

# Python代码审查报告

**生成时间:** 2026-02-24 21:33:11
**项目路径:** /Users/bytedance/Desktop/常见python/manju_web

## 1. 项目概览

| 指标 | 数值 |
|------|------|
| Python文件数 | 88 |
| 总行数 | 29,792 |
| 代码行数 | 25,515 |
| 类总数 | 94 |
| 函数/方法总数 | 911 |

**检测到的包:**

- backend
- backend.handlers
- backend.repositories
- backend.services
- backend.services.workflow_runtime

## 2. 超长函数/方法检测

**发现 262 个超长/复杂函数:**

### 🔴 严重问题

**/Users/bytedance/Desktop/常见python/manju_web/backend/server.py:143**
- 函数: `send_file`
- 行数: 52, 复杂度: 13

**/Users/bytedance/Desktop/常见python/manju_web/backend/server.py:419**
- 函数: `build_character_details`
- 行数: 60, 复杂度: 33

**/Users/bytedance/Desktop/常见python/manju_web/backend/server.py:539**
- 函数: `build_fenjing_details`
- 行数: 87, 复杂度: 26

**/Users/bytedance/Desktop/常见python/manju_web/backend/server.py:628**
- 函数: `list_project_assets`
- 行数: 89, 复杂度: 22

**/Users/bytedance/Desktop/常见python/manju_web/backend/server.py:805**
- 函数: `run_cloth_changed_regen`
- 行数: 67, 复杂度: 27

### 🟡 一般问题

**/Users/bytedance/Desktop/常见python/manju_web/backend/server.py:302** - `stringify_characters` (15 行)
**/Users/bytedance/Desktop/常见python/manju_web/backend/server.py:395** - `resolve_location_image` (22 行)
**/Users/bytedance/Desktop/常见python/manju_web/backend/server.py:488** - `build_cloth_changed_details` (49 行)
**/Users/bytedance/Desktop/常见python/manju_web/backend/server.py:770** - `run_character_regen` (33 行)
**/Users/bytedance/Desktop/常见python/manju_web/backend/server.py:874** - `run_fenjing_regen` (34 行)


## 3. 冗余与重复代码检测

✅ 未发现重复代码问题

## 4. 线程安全检测

✅ 未发现线程安全问题

## 5. 代码内聚性与耦合度分析

✅ 未发现明显的内聚性问题

## 6. 总结与建议

**问题汇总:**

- 严重问题 (CRITICAL): 0
- 错误 (ERROR): 0
- 警告 (WARNING): 0

**优先处理建议:**

2. **🟡 重构过长函数**
   - 将行数超过50行的函数拆分
   - 降低圈复杂度（目标 < 10）
   - 减少函数参数数量

3. **🔵 消除重复代码**
   - 提取公共函数/方法
   - 使用继承或组合复用代码
   - 清理未使用的导入和函数

4. **🟢 改善代码内聚性**
   - 确保每个类有明确的单一职责
   - 减少类之间的耦合
   - 提取通用接口提高可复用性

---

*报告由 Python代码审查工具生成*
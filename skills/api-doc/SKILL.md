---
name: api-doc
description: 为 manju_web 后端 API 生成结构化文档与变更摘要。当用户需要接口列表、参数说明、响应结构或基于代码的接口说明时使用。
---

# Skill: ApiDoc

## Description
针对 `/Users/bytedance/Desktop/常见python/manju_web` 项目的 API 文档生成技能。
输出基于代码事实的接口清单与结构化说明。

## Workflow

### Step 1: 入口与路由梳理
1. 使用 `skills/api-doc/scripts/api_doc_scan.py` 扫描路由匹配模式，生成基础接口清单。
2. 读取 `backend/server.py` 与 `backend/handlers/*.py`，定位路由注册与处理逻辑。
3. 归类接口的 HTTP Method、路径、路径参数与 Query 参数来源。

### Step 2: 请求与响应结构提取
1. 追踪每个 Handler 使用的服务与仓库层函数，提取关键字段与约束。
2. 提供响应 JSON 的关键字段结构与类型约束。

### Step 3: 文档输出
1. 以“接口列表 + 单接口详情”的形式输出。
2. 对变更点输出“变更摘要”，说明新增/调整/废弃接口。
3. 默认仅在对话中输出，不创建文件，除非用户明确要求落盘。

## Constraints
- 仅基于实际代码内容描述，不做推测。
- 体现请求校验规则与错误响应路径。
- 优先引用已有接口的统一错误格式与状态码。

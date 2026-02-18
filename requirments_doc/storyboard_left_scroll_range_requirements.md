# 需求文档：storyboard-left 滚动范围限制优化

## 1. 需求概述

### 1.1 背景
`storyboard-left` 区域（角色图列表、分镜列表等）使用 `max-height: calc(100vh - 280px)` 计算高度，当页面底部存在 `project-bottom` 面板（任务状态）时，滚动到底部的内容会被遮挡。

### 1.2 目标
限制 `storyboard-left` 的滚动范围，确保其内容不会被底部面板遮挡。

---

## 2. EARS 需求分析

### 2.1 功能需求

| ID | Event | Actor | Request | Scope |
|----|-------|-------|---------|-------|
| FR-001 | 用户滚动 storyboard-left 列表 | 系统 | 滚动范围不超过 project-content 区域 | storyboard-left 组件 |
| FR-002 | 页面底部有 project-bottom 面板 | 系统 | storyboard-left 内容不被遮挡 | 所有使用 storyboard-left 的页面 |

### 2.2 非功能需求

| ID | 类型 | 描述 |
|----|------|------|
| NFR-001 | 可用性 | 滚动体验流畅，无视觉跳动 |
| NFR-002 | 兼容性 | 不影响现有页面布局和功能 |
| NFR-003 | 响应式 | 适应不同屏幕高度和底部面板高度 |

---

## 3. 影响评估

### 3.1 影响范围

| 文件 | 影响类型 | 影响程度 |
|------|----------|----------|
| `frontend/style.css` | CSS 样式修改 | 中 |
| `frontend/app.js` | 可能需要修改 | 低 |
| `frontend/index.html` | 无需修改 | 无 |

### 3.2 受影响的页面

- 角色图页面 (`tabCharacters`)
- 换装图页面 (`tabClothChanged`)
- 场景图页面 (`tabLocations`)
- 章节分镜页面 (`tabStoryboards`)

---

## 4. 验收标准

| ID | 验收条件 |
|----|----------|
| AC-001 | 滚动 storyboard-left 到底部时，内容不被 project-bottom 遮挡 |
| AC-002 | 不同屏幕高度下，滚动范围正确计算 |
| AC-003 | 底部面板显示/隐藏时，滚动范围自适应 |
| AC-004 | 滚动体验流畅，无视觉跳动 |

---

## 5. 约束条件

- 优先使用纯 CSS 方案
- 如 CSS 无法实现，再考虑 JavaScript 方案
- 保持现有功能不变

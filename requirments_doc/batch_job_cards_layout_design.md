# 设计文档：Batch 页面任务卡片布局优化

## 1. 技术方案

### 1.1 方案概述
通过修改 CSS 样式，将任务卡片从竖向排列改为横向排列，并添加横向滚动功能。

### 1.2 技术选型

| 技术点 | 方案 | 说明 |
|--------|------|------|
| 布局方式 | Flexbox | 使用 `flex-direction: row` 实现横向排列 |
| 滚动方式 | `overflow-x: auto` | 支持横向滚轮滚动 |
| 卡片宽度 | 固定宽度 | 每个卡片固定宽度，保证一致性 |
| 滚动条样式 | 自定义样式 | 美化滚动条外观 |

---

## 2. CSS 设计

### 2.1 容器样式修改

**修改文件**: `frontend/style.css`

**当前样式** (第95-99行):
```css
.list {
  display: flex;
  flex-direction: column;  /* 竖向排列 */
  gap: 6px;
}
```

**修改后样式**:
```css
.list {
  display: flex;
  flex-direction: row;     /* 横向排列 */
  gap: 12px;
  overflow-x: auto;        /* 横向滚动 */
  padding-bottom: 8px;     /* 为滚动条留出空间 */
  scroll-behavior: smooth; /* 平滑滚动 */
}
```

### 2.2 任务卡片样式修改

**当前样式** (第118-126行):
```css
.job-item {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(6, 10, 22, 0.7);
  border: 1px solid rgba(56, 189, 248, 0.12);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
```

**修改后样式**:
```css
.job-item {
  min-width: 320px;        /* 固定最小宽度 */
  max-width: 320px;        /* 固定最大宽度 */
  flex-shrink: 0;          /* 防止压缩 */
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(6, 10, 22, 0.7);
  border: 1px solid rgba(56, 189, 248, 0.12);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
```

### 2.3 滚动条样式

**新增样式**:
```css
/* 自定义滚动条样式 */
.list::-webkit-scrollbar {
  height: 6px;
}

.list::-webkit-scrollbar-track {
  background: rgba(10, 15, 30, 0.5);
  border-radius: 3px;
}

.list::-webkit-scrollbar-thumb {
  background: rgba(56, 189, 248, 0.4);
  border-radius: 3px;
}

.list::-webkit-scrollbar-thumb:hover {
  background: rgba(56, 189, 248, 0.6);
}
```

---

## 3. 布局示意图

### 3.1 修改前（竖向排列）

```
┌─────────────────────────────────────┐
│ 任务卡片 1                           │
├─────────────────────────────────────┤
│ 任务卡片 2                           │
├─────────────────────────────────────┤
│ 任务卡片 3                           │
├─────────────────────────────────────┤
│ 任务卡片 4                           │
└─────────────────────────────────────┘
```

### 3.2 修改后（横向排列 + 滚动）

```
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ───▶
│ 任务卡片 1   │ │ 任务卡片 2   │ │ 任务卡片 3   │ │ 任务卡片 4   │ 滚动
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
```

---

## 4. 兼容性考虑

### 4.1 保持不变的内容

| 内容 | 说明 |
|------|------|
| HTML 结构 | 无需修改 |
| JavaScript 逻辑 | 无需修改 |
| 卡片内部布局 | 保持竖向排列 |
| 状态样式 | success/error/running 样式不变 |
| 动画效果 | 呼吸动画保持 |

### 4.2 响应式考虑

- 卡片固定宽度 320px，保证内容一致性
- 容器支持横向滚动，适应不同屏幕宽度
- 滚动条样式与整体设计风格一致

---

## 5. 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 小屏幕显示问题 | 低 | 横向滚动解决 |
| 滚动条样式兼容性 | 低 | 使用标准 webkit 样式 |
| 卡片内容溢出 | 低 | 固定宽度 + 内部滚动 |

---

## 6. 验证方案

1. 打开 Batch 页面，确认任务卡片横向排列
2. 使用滚轮横向滚动，确认滚动流畅
3. 确认卡片内容显示正常
4. 确认不同状态的卡片样式正常
5. 确认运行中卡片的动画效果正常

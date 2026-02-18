# 设计文档：storyboard-left 滚动范围限制优化

## 1. 技术方案

### 1.1 方案对比

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| 方案A | 调整 max-height 计算值 | 简单 | 底部面板高度不固定，难以精确计算 |
| 方案B | JavaScript 动态计算高度 | 精确 | 需要监听窗口变化，性能开销 |
| **方案C** | **CSS Flexbox 布局优化** | **纯 CSS，自适应** | **需要调整页面布局结构** |

### 1.2 推荐方案：方案C - CSS Flexbox 布局优化

**核心思路**：
1. 让 `project-view` 使用 `flex` 布局
2. 让 `project-content` 自动填充剩余空间（`flex: 1`）
3. `project-bottom` 固定在底部
4. `storyboard-left` 的 `max-height` 基于 `project-content` 的高度

---

## 2. CSS 设计

### 2.1 修改 `.project-view` 布局

**当前样式** (第1765-1770行):
```css
.project-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px 28px 40px;
}
```

**修改后样式**:
```css
.project-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px 28px 40px;
  min-height: calc(100vh - 40px);  /* 确保占满视口 */
}
```

### 2.2 修改 `.project-content` 布局

**当前样式** (第1805-1809行):
```css
.project-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
```

**修改后样式**:
```css
.project-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;              /* 自动填充剩余空间 */
  min-height: 0;        /* 允许收缩 */
  overflow: hidden;     /* 防止溢出 */
}
```

### 2.3 修改 `.tab-panel` 布局

**当前样式** (第1797-1803行):
```css
.tab-panel {
  background: rgba(15, 23, 42, 0.75);
  border-radius: 14px;
  padding: 16px;
  box-shadow: 0 10px 30px rgba(8, 14, 30, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.18);
}
```

**修改后样式**:
```css
.tab-panel {
  background: rgba(15, 23, 42, 0.75);
  border-radius: 14px;
  padding: 16px;
  box-shadow: 0 10px 30px rgba(8, 14, 30, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.18);
  flex: 1;              /* 自动填充剩余空间 */
  min-height: 0;        /* 允许收缩 */
  overflow: hidden;     /* 防止溢出 */
}
```

### 2.4 修改 `.storyboard-layout` 布局

**当前样式** (第1821-1825行):
```css
.storyboard-layout {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 16px;
}
```

**修改后样式**:
```css
.storyboard-layout {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 16px;
  height: 100%;         /* 占满父容器 */
  min-height: 0;        /* 允许收缩 */
}
```

### 2.5 修改 `.storyboard-left` 布局

**当前样式** (第1831-1838行):
```css
.storyboard-left {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: calc(100vh - 280px);
  overflow-y: auto;
  overflow-x: hidden;
}
```

**修改后样式**:
```css
.storyboard-left {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 100%;     /* 基于父容器高度 */
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;        /* 允许收缩 */
}
```

---

## 3. 布局示意图

### 3.1 修改前

```
┌─────────────────────────────────────┐
│ project-view (无高度限制)            │
│ ┌─────────────────────────────────┐ │
│ │ project-header                  │ │
│ └─────────────────────────────────┘ │
│ ┌─────────────────────────────────┐ │
│ │ project-main-tabs               │ │
│ └─────────────────────────────────┘ │
│ ┌─────────────────────────────────┐ │
│ │ project-content                 │ │
│ │ ┌─────────────────────────────┐ │ │
│ │ │ tab-panel                   │ │ │
│ │ │ ┌───────────┬─────────────┐ │ │ │
│ │ │ │left(固定) │ right       │ │ │ │
│ │ │ │max-height │             │ │ │ │
│ │ │ │calc(100vh │             │ │ │ │
│ │ │ │- 280px)   │             │ │ │ │
│ │ │ └───────────┴─────────────┘ │ │ │
│ │ └─────────────────────────────┘ │ │
│ └─────────────────────────────────┘ │
│ ┌─────────────────────────────────┐ │
│ │ project-bottom (遮挡内容)       │ │
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

### 3.2 修改后

```
┌─────────────────────────────────────┐
│ project-view (min-height: 100vh)    │
│ ┌─────────────────────────────────┐ │
│ │ project-header (固定高度)        │ │
│ └─────────────────────────────────┘ │
│ ┌─────────────────────────────────┐ │
│ │ project-main-tabs (固定高度)     │ │
│ └─────────────────────────────────┘ │
│ ┌─────────────────────────────────┐ │
│ │ project-content (flex: 1)       │ │ ← 自动填充剩余空间
│ │ ┌─────────────────────────────┐ │ │
│ │ │ tab-panel (flex: 1)         │ │ │ ← 自动填充
│ │ │ ┌───────────┬─────────────┐ │ │ │
│ │ │ │left       │ right       │ │ │ │
│ │ │ │max-height │             │ │ │ │
│ │ │ │: 100%     │             │ │ │ │ ← 基于父容器
│ │ │ │(不遮挡)   │             │ │ │ │
│ │ │ └───────────┴─────────────┘ │ │ │
│ │ └─────────────────────────────┘ │ │
│ └─────────────────────────────────┘ │
│ ┌─────────────────────────────────┐ │
│ │ project-bottom (固定在底部)      │ │
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

---

## 4. 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 布局变化影响其他页面 | 中 | 只修改必要的样式属性 |
| 小屏幕显示问题 | 低 | 使用 `min-height: 0` 允许收缩 |
| 兼容性问题 | 低 | Flexbox 广泛支持 |

---

## 5. 验证方案

1. 打开角色图页面，滚动列表到底部，确认不被遮挡
2. 打开分镜页面，滚动列表到底部，确认不被遮挡
3. 调整浏览器窗口大小，确认布局自适应
4. 切换不同 Tab，确认布局正常

# 实现计划：Batch 页面任务卡片布局优化

## 任务列表

### 任务 1: 修改 .list 容器样式
- [x] 将 `flex-direction: column` 改为 `flex-direction: row`
- [x] 添加 `overflow-x: auto` 支持横向滚动
- [x] 添加 `padding-bottom: 8px` 为滚动条留出空间
- [x] 添加 `scroll-behavior: smooth` 平滑滚动
- [x] 将 `gap` 从 `6px` 改为 `12px`

### 任务 2: 修改 .job-item 卡片样式
- [x] 添加 `min-width: 320px` 固定最小宽度
- [x] 添加 `max-width: 320px` 固定最大宽度
- [x] 添加 `flex-shrink: 0` 防止卡片被压缩

### 任务 3: 添加滚动条样式
- [x] 添加 `.list::-webkit-scrollbar` 样式（高度 6px）
- [x] 添加 `.list::-webkit-scrollbar-track` 样式（轨道背景）
- [x] 添加 `.list::-webkit-scrollbar-thumb` 样式（滑块颜色）
- [x] 添加 `.list::-webkit-scrollbar-thumb:hover` 样式（悬停效果）

### 任务 4: 验证测试
- [ ] 刷新页面，确认任务卡片横向排列
- [ ] 测试滚轮横向滚动功能
- [ ] 确认卡片内容显示正常
- [ ] 确认不同状态（success/error/running）样式正常
- [ ] 确认运行中卡片的动画效果正常

---

## 文件修改清单

| 文件 | 修改类型 | 修改行数 |
|------|----------|----------|
| `frontend/style.css` | CSS 样式修改 | ~30 行 |

---

## 预估工作量

| 任务 | 预估时间 |
|------|----------|
| 任务 1: 修改 .list 容器样式 | 2 分钟 |
| 任务 2: 修改 .job-item 卡片样式 | 1 分钟 |
| 任务 3: 添加滚动条样式 | 3 分钟 |
| 任务 4: 验证测试 | 2 分钟 |
| **总计** | **8 分钟** |

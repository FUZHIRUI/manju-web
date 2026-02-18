# 实现计划：storyboard-left 滚动范围限制优化

## 任务列表

### 任务 1: 修改 .project-view 布局
- [x] 添加 `min-height: calc(100vh - 40px)` 确保占满视口

### 任务 2: 修改 .project-content 布局
- [x] 添加 `flex: 1` 自动填充剩余空间
- [x] 添加 `min-height: 0` 允许收缩
- [x] 添加 `overflow: hidden` 防止溢出

### 任务 3: 修改 .tab-panel 布局
- [x] 添加 `flex: 1` 自动填充剩余空间
- [x] 添加 `min-height: 0` 允许收缩
- [x] 添加 `overflow: hidden` 防止溢出

### 任务 4: 修改 .storyboard-layout 布局
- [x] 添加 `height: 100%` 占满父容器
- [x] 添加 `min-height: 0` 允许收缩

### 任务 5: 修改 .storyboard-left 布局
- [x] 将 `max-height: calc(100vh - 280px)` 改为 `max-height: 100%`
- [x] 添加 `min-height: 0` 允许收缩

### 任务 6: 验证测试
- [x] 打开角色图页面，滚动列表到底部，确认不被遮挡
- [x] 打开分镜页面，滚动列表到底部，确认不被遮挡
- [x] 调整浏览器窗口大小，确认布局自适应
- [x] 切换不同 Tab，确认布局正常

---

## 文件修改清单

| 文件 | 修改类型 | 修改行数 |
|------|----------|----------|
| `frontend/style.css` | CSS 样式修改 | ~15 行 |

---

## 预估工作量

| 任务 | 预估时间 |
|------|----------|
| 任务 1: 修改 .project-view 布局 | 1 分钟 |
| 任务 2: 修改 .project-content 布局 | 2 分钟 |
| 任务 3: 修改 .tab-panel 布局 | 2 分钟 |
| 任务 4: 修改 .storyboard-layout 布局 | 1 分钟 |
| 任务 5: 修改 .storyboard-left 布局 | 1 分钟 |
| 任务 6: 验证测试 | 3 分钟 |
| **总计** | **10 分钟** |

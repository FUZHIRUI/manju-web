# 常见问题排查指南

本文档记录了 manju_web 项目中常见的问题及其排查方法。

## 1. 后端服务问题

### 1.1 服务无法启动

**症状**：
- 运行 `python server.py` 后立即退出
- 端口被占用错误
- 导入错误

**排查步骤**：
1. 检查端口 8086 是否被占用：
   ```bash
   lsof -i :8086
   ```
2. 检查 Python 依赖是否完整：
   ```bash
   pip list
   ```
3. 查看启动日志中的详细错误信息

### 1.2 API 请求返回 500 错误

**症状**：
- 前端请求失败，控制台显示 500 Internal Server Error
- 后端日志中有 Traceback

**排查步骤**：
1. 查看 `backend/logs/` 下的最新日志文件
2. 定位 Traceback 中的错误位置
3. 检查相关 Handler 和 Service 代码
4. 验证数据库/文件存储是否正常

## 2. 前端问题

### 2.1 页面空白或加载失败

**症状**：
- 打开 index.html 后页面空白
- 控制台显示 JavaScript 错误

**排查步骤**：
1. 打开浏览器开发者工具（F12）
2. 查看 Console 标签页的错误信息
3. 查看 Network 标签页，确认资源是否加载成功
4. 检查后端服务是否正常运行

### 2.2 按钮点击无响应

**症状**：
- 点击按钮后没有任何反应
- 控制台没有错误信息

**排查步骤**：
1. 检查按钮的事件监听器是否正确绑定
2. 在 `app.js` 中相关函数处添加 console.log
3. 检查 Network 标签页，确认 API 请求是否发出
4. 验证按钮是否被其他元素遮挡

## 3. 工作流状态问题

### 3.1 状态不更新

**症状**：
- 执行操作后状态保持不变
- 刷新页面后状态才更新

**排查步骤**：
1. 检查后端状态更新逻辑
2. 确认前端状态刷新机制
3. 查看 `status_service.py` 和相关 Repository
4. 验证数据库/JSON 文件中的状态值

### 3.2 状态流转错误

**症状**：
- 状态跳转到了错误的状态
- 状态卡在某个中间状态

**排查步骤**：
1. 查看 `workflow_service.py` 中的状态机逻辑
2. 检查状态转换条件
3. 查看日志中的状态变更记录
4. 验证触发状态变更的条件是否满足

## 4. 数据问题

### 4.1 数据丢失

**症状**：
- 刷新页面后数据消失
- 项目或 Job 找不到

**排查步骤**：
1. 检查数据存储位置（`backend/data/` 或 `backend/manju_output/`）
2. 确认文件权限是否正确
3. 查看 Repository 层的读写逻辑
4. 检查是否有并发写入问题

### 4.2 数据格式错误

**症状**：
- JSON 解析错误
- 数据字段缺失或类型错误

**排查步骤**：
1. 检查数据文件的格式
2. 验证序列化/反序列化逻辑
3. 查看相关数据模型定义
4. 确认数据写入时的验证逻辑

## 5. 换装功能相关问题

### 5.1 按钮并行执行问题

**症状**：
- 点击换装按钮后创建了多个 Job，举个例子：
- `cloth_images` 和 `cloth_changed` 没有串行执行

**相关文件**：
- `frontend/app.js` - 按钮点击处理逻辑
- `backend/services/job_service.py` - Job 创建逻辑
- `backend/services/workflow_service.py` - 工作流执行逻辑

**排查步骤**：
1. 检查 `frontend/app.js` 中的 `appendVisualAudioPhaseButtons` 函数
2. 确认按钮点击时是否只调用了一次 `submitFlowPhase`
3. 查看 phase 参数是否正确传递为 "cloth_images,cloth_changed"
4. 检查后端如何处理逗号分隔的 phase 参数

### 5.2 换装状态异常

**症状**：
- `cloth_images` 状态一直是 running
- `cloth_changed` 没有开始执行

**排查步骤**：
1. 查看工作流状态流转逻辑
2. 检查 phase 完成的判断条件
3. 确认下一个 phase 的触发机制
4. 查看日志中的执行记录

## 6. 调试技巧

### 6.1 日志调试

1. 在关键位置添加日志：
   ```python
   import logging
   logger = logging.getLogger(__name__)
   logger.info(f"Processing phase: {phase}, status: {status}")
   ```

2. 实时查看日志：
   ```bash
   tail -f backend/logs/app.log
   ```

### 6.2 前端调试

1. 使用 `debugger` 语句暂停执行
2. 使用 `console.log` 输出变量值
3. 使用 Network 标签页查看请求详情
4. 使用 Elements 标签页检查 DOM 结构

### 6.3 API 测试

使用 curl 或 Postman 直接测试 API：

```bash
# 获取项目列表
curl http://127.0.0.1:8086/api/projects

# 提交流程阶段
curl -X POST http://127.0.0.1:8086/api/projects/{project_id}/submit-flow-phase \
  -H "Content-Type: application/json" \
  -d '{"phase": "cloth_images,cloth_changed"}'
```

# Manju Web 工作流故障排查指南

## 常见问题及解决方案

### 1. 服务连接问题

#### 问题: Connection refused / ConnectionError
**症状**: 
```
requests.exceptions.ConnectionError: HTTPConnectionPool(host='127.0.0.1', port=8086)
```

**原因**: 后端服务未启动或端口被占用

**解决方案**:
```bash
# 检查服务状态
curl http://127.0.0.1:8086/api/projects

# 如果无响应，重启服务（假设当前在项目根目录）
lsof -ti:8086 | xargs kill -9
sleep 2
cd backend
python server.py > logs/server.log 2>&1 &
```

**自动恢复**: 工作流执行器会自动检测并尝试重启服务

---

### 2. 超时问题

#### 问题: Timeout waiting for flow to complete
**症状**: 
```
TimeoutError: Timeout waiting for auto_storyboard to complete
```

**原因**: 
- 任务执行时间过长
- 网络延迟
- 服务处理缓慢

**解决方案**:
1. 增加超时时间（默认5分钟，可增加到10-20分钟）
2. 检查服务日志是否有错误
3. 手动检查任务状态

**自动恢复**: 工作流执行器会自动将超时时间翻倍后重试

---

### 3. TOS Presign失败

#### 问题: Failed to get presigned URL
**症状**: 
```
ERROR: Failed to get presigned URL for fenjing image
```

**原因**:
- TOS配置错误
- 鉴权失败
- 网络问题

**解决方案**:
1. 检查 `backend/services/workflow_runtime/runtime_config.py` 中的TOS配置
2. 验证AK/SK是否正确
3. 检查TOS bucket是否存在且可访问

**相关文件**:
- `backend/services/workflow_runtime/provider_runtime.py`
- `backend/services/workflow_runtime/runtime_config.py`

---

### 4. Print I/O错误

#### 问题: I/O operation on closed file
**症状**: 
```
ValueError: I/O operation on closed file.
File "provider_runtime.py", line 139, in emit_event
```

**原因**: 
- 多线程环境下 `sys.stdout` 被关闭
- `redirect_stdout` 线程不安全

**解决方案**:
已修复！使用 `ThreadLogRedirector` 替代 `redirect_stdout`

**相关文件**:
- `backend/services/workflow_runtime/thread_safe_logging.py`
- `backend/services/workflow_service.py`

**验证修复**:
```bash
# 检查是否还有redirect_stdout使用
grep -rn "redirect_stdout" backend/services/ --include="*.py"
# 应该只返回server.py中的子进程使用（这是安全的）
```

---

### 5. 状态重置问题

#### 问题: 已完成的步骤被重置为running
**症状**: 
- `character_images` 已经是 `completed`
- 执行TTS后，`character_images` 变成 `running`

**原因**: 
- `flow_start` 事件重置所有步骤状态
- `update_from_event` 函数中的逻辑问题

**解决方案**:
已修复！`flow_start` 时不再重置已完成的步骤

**相关文件**:
- `backend/services/status_service.py`

**修复代码**:
```python
# 修复前
if event == "flow_start":
    _reset_all_steps(state, flow)  # 重置所有步骤

# 修复后
if event == "flow_start":
    # 只重置当前要执行的步骤
    for step_id in step_ids:
        current_status = state.get("flows", {}).get(flow, {}).get("steps", {}).get(step_id, _STATUS_WAITING)
        if current_status != _STATUS_COMPLETED:
            _set_step_status(state, flow, step_id, _STATUS_RUNNING)
```

---

### 6. 鉴权失败

#### 问题: 401 Unauthorized
**症状**: 
```
HTTP 401: Unauthorized
```

**原因**: 
- API Key过期
- 权限不足
- 请求头缺失

**解决方案**:
1. 检查API Key是否有效
2. 检查请求是否包含正确的认证头
3. 重新生成API Key

**注意**: 此问题通常不可自动恢复，需要人工介入

---

### 7. 磁盘空间不足

#### 问题: No space left on device
**症状**: 
```
OSError: [Errno 28] No space left on device
```

**解决方案**:
```bash
# 检查磁盘空间
df -h

# 清理日志文件
rm -rf backend/logs/*.log

# 清理旧项目
rm -rf manju_output/old_project

# 清理缓存
find backend -name "*.pyc" -delete
find backend -name "__pycache__" -type d -exec rm -rf {} +
```

---

### 8. Playwright前端操作失败

#### 问题: 元素未找到或不可点击
**症状**: 
```
TimeoutError: Waiting for selector ".task-card:has-text('分镜图生成')"
```

**原因**:
- 页面加载未完成
- 元素选择器错误
- 前端状态不一致

**解决方案**:
1. 增加等待时间
2. 检查页面截图，确认元素是否存在
3. 刷新页面后重试

**调试方法**:
```python
# 在失败时自动截图
screenshot_path = controller.take_screenshot("error_state")
print(f"错误状态截图: {screenshot_path}")
```

---

## 调试技巧

### 1. 查看日志
```bash
# 查看最新日志
tail -f backend/logs/server.log

# 搜索错误
grep -i "error\|exception\|traceback" backend/logs/*.log

# 查看特定时间段的日志
grep "2026-02-17 10:" backend/logs/server.log
```

### 2. 检查服务状态
```bash
# 检查进程
ps aux | grep "python.*server"

# 检查端口
lsof -i :8086

# 测试API
curl http://127.0.0.1:8086/api/projects
```

### 3. 检查产物文件
```bash
# 列出项目产物
ls -la manju_output/{project}/

# 检查文件大小
find manju_output/{project} -type f -exec ls -lh {} \;

# 检查JSON文件是否有效
python -m json.tool manju_output/{project}/storyboard_assets/chapters.jsonl > /dev/null && echo "Valid JSON"
```

### 4. 使用Bug Fix技能
当遇到无法解决的问题时，可以调用bug-fixer技能：

```python
from exception_handler import ExceptionHandler

handler = ExceptionHandler(config)
diagnosis = handler.diagnose(step, result)

if diagnosis["requires_bug_fix"]:
    bug_report = handler.invoke_bug_fix_skill(diagnosis)
    print(f"Bug报告: {bug_report['report_path']}")
```

---

## 联系支持

如果以上方法都无法解决问题：
1. 收集完整的日志文件
2. 保存错误截图
3. 记录复现步骤
4. 提交Bug报告

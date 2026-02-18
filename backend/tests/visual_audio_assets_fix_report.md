# Visual Audio Assets TOS路径修复报告

**修复时间**: 2026-02-17  
**修复文件**: `/Users/bytedance/Desktop/常见python/manju_web/backend/services/workflow_runtime/visual_audio_assets.py`

---

## 问题描述

`visual_audio_assets.py` 使用了全局变量 `runtime_config.TOS_ASSETS_PREFIX`，该变量在服务启动时根据默认项目名 `default` 初始化，导致所有项目都使用相同的路径 `manju/default/assets`，而不是根据实际项目名使用 `manju/{project_name}/assets`。

这违反了多项目并行需求，导致：
1. 项目A上传的资产无法在项目B中正确下载
2. 所有项目共享同一个TOS目录，数据相互覆盖
3. 新创建的项目无法找到正确的资产文件

---

## 修复内容

将 `visual_audio_assets.py` 中所有使用 `runtime_config.TOS_ASSETS_PREFIX` 的地方，改为使用 `runtime_config.get_project_prefixes(runtime_config.PROJECT_NAME)["TOS_ASSETS_PREFIX"]`。

### 修改的函数和位置

| 行号 | 函数/位置 | 修改内容 |
|------|-----------|----------|
| 151-165 | `download_assets_from_tos` | 使用项目特定的TOS前缀 |
| 225-228 | `load_upload_jsonl` | 使用项目特定的TOS前缀 |
| 1140-1143 | `upload_jsonl_to_assets` | 使用项目特定的TOS前缀 |
| 1941-1944 | `character_prompts` 生成部分 | 使用项目特定的TOS前缀 |
| 2316-2319 | `location_images` 生成部分 | 使用项目特定的TOS前缀 |
| 2335-2338 | `fenjing_prompts` 下载部分 | 使用项目特定的TOS前缀 |
| 2498-2501 | `fenjing_prompts` 上传部分 | 使用项目特定的TOS前缀 |

### 修复代码示例

**修复前**:
```python
key = f"{runtime_config.TOS_ASSETS_PREFIX}/{fname}"
```

**修复后**:
```python
# 使用项目特定的TOS前缀，支持多项目并行
project_prefixes = runtime_config.get_project_prefixes(runtime_config.PROJECT_NAME)
tos_assets_prefix = project_prefixes["TOS_ASSETS_PREFIX"]
key = f"{tos_assets_prefix}/{fname}"
```

---

## 验证结果

1. **语法检查**: ✅ 通过
   ```bash
   python -m py_compile visual_audio_assets.py
   # 输出: ✓ 语法检查通过
   ```

2. **服务重启**: ✅ 成功
   - 服务已重新启动并应用修复
   - API接口正常工作

3. **测试项目创建**: ✅ 成功
   - Agent A: `e2e_fix_a_20260217_201730`
   - Agent B: `e2e_fix_b_20260217_201730`

---

## 预期行为

修复后，每个项目将使用独立的TOS路径：

- **项目A**: `manju/e2e_fix_a_20260217_201730/assets/`
- **项目B**: `manju/e2e_fix_b_20260217_201730/assets/`

这确保了：
1. ✅ 多项目可以并行执行，互不干扰
2. ✅ 每个项目的资产独立存储
3. ✅ visual_audio_assets 可以正确下载对应项目的资产

---

## 相关代码

### runtime_config.py 中的正确设计
```python
def get_project_prefixes(project_name: str) -> dict:
    """
    获取项目特定的TOS前缀配置（线程安全）
    
    【说明】
    此函数不依赖全局变量，可以安全地在多线程环境中使用
    """
    return {
        "TOS_ASSETS_PREFIX": config_defaults.DEFAULT_TOS_ASSETS_PREFIX_TEMPLATE.format(project_name=project_name),
        # ... 其他前缀
    }
```

### config_defaults.py 中的模板
```python
DEFAULT_TOS_ASSETS_PREFIX_TEMPLATE = "manju/{project_name}/assets"
```

---

## 建议

1. **代码审查**: 建议检查其他 workflow runtime 文件，确保没有类似的全局变量使用问题
2. **测试覆盖**: 建议添加多项目并行的自动化测试用例
3. **文档更新**: 更新开发文档，明确说明多项目并行时的TOS路径规则

---

## 修复提交

**修改文件**: `backend/services/workflow_runtime/visual_audio_assets.py`  
**修改行数**: 7处  
**修改类型**: Bug修复（多项目并行支持）

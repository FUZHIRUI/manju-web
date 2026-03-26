import os

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_EMPTY_STRING = ""  # 统一空值占位，避免 None 传播
DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"  # 默认使用官方网关，便于直接联通
DEFAULT_ARK_API_KEY = DEFAULT_EMPTY_STRING  # 默认留空，避免误用明文密钥
DEFAULT_ARK_CHAT_MODEL = DEFAULT_EMPTY_STRING  # 默认留空，强制显式指定模型
DEFAULT_ARK_VLM_MODEL = DEFAULT_EMPTY_STRING  # 默认留空，避免误用视觉模型
DEFAULT_SEEDREAM_MODEL = DEFAULT_EMPTY_STRING  # 默认留空，避免误调用绘图模型
DEFAULT_ARK_TIMEOUT = 1800  # 给予长超时，覆盖大模型长响应
DEFAULT_ARK_MODEL_QPS = 0.0  # 0 表示不限制，交由统一限流处理
DEFAULT_ARK_MODEL_CONCURRENCY = 0  # 0 表示不限制，交由统一并发控制

DEFAULT_OUTPUT_DIR = os.path.join(_BACKEND_DIR, "manju_output")  # 固定在 backend/manju_output，避免启动目录影响
DEFAULT_PROJECT_NAME = DEFAULT_EMPTY_STRING  # 默认不设置项目名，避免误写入错误目录
DEFAULT_TOS_ENDPOINT = "tos-cn-beijing.volces.com"  # 默认使用北京节点，减少跨区延迟
DEFAULT_TOS_ACCESS_KEY = DEFAULT_EMPTY_STRING  # 默认留空，避免误写入凭证
DEFAULT_TOS_SECRET_KEY = DEFAULT_EMPTY_STRING  # 默认留空，避免误写入凭证
DEFAULT_TOS_REGION = "cn-beijing"  # 默认区域与端点保持一致
DEFAULT_TOS_BUCKET = DEFAULT_EMPTY_STRING  # 默认留空，强制显式配置桶
DEFAULT_TOS_PROJECT_NAME = "default"  # 缺省项目名用于无 PROJECT_NAME 场景
DEFAULT_TOS_ASSETS_PREFIX_TEMPLATE = "manju/{project_name}/assets"  # 默认资产前缀保持统一目录结构
DEFAULT_TOS_CHARACTER_PREFIX_TEMPLATE = "manju/{project_name}/character"  # 默认人物素材路径规约
DEFAULT_TOS_LOCATION_PREFIX_TEMPLATE = "manju/{project_name}/location"  # 默认场景素材路径规约
DEFAULT_TOS_CLOTH_PREFIX_TEMPLATE = "manju/{project_name}/cloth"  # 默认服饰素材路径规约
DEFAULT_TOS_CROP_ROLE_PREFIX_TEMPLATE = "manju/{project_name}/crop_role"  # 默认裁剪素材路径规约
DEFAULT_TOS_FENJING_PREFIX_TEMPLATE = "manju/{project_name}/fenjing"  # 默认分镜素材路径规约
DEFAULT_TOS_TTS_PREFIX_TEMPLATE = "manju/{project_name}/tts"  # 默认音频素材路径规约
DEFAULT_TOS_VIDEO_PREFIX_TEMPLATE = "manju/{project_name}/video"  # 默认视频素材路径规约

DEFAULT_TTS_APP_ID = DEFAULT_EMPTY_STRING  # 默认留空，避免误用凭证
DEFAULT_TTS_ACCESS_KEY = DEFAULT_EMPTY_STRING  # 默认留空，避免误用凭证
DEFAULT_TTS_RESOURCE_ID = DEFAULT_EMPTY_STRING  # 默认留空，强制显式指定资源
DEFAULT_TTS_URL = DEFAULT_EMPTY_STRING  # 默认留空，避免调用错误域名
DEFAULT_TTS_SPEAKER = DEFAULT_EMPTY_STRING  # 默认留空，避免选错音色
DEFAULT_TTS_TOTAL_CONCURRENCY = 10  # 默认限制全局并发，避免过载

DEFAULT_STORYBOARD_BATCH_SIZE = 3  #每次生章节的批次

DEFAULT_PHASE1_THINKING = "enabled"  # 默认开启思考，提升阶段一生成质量
DEFAULT_PHASE1_REASONING_EFFORT = "high"  # 默认中等推理强度，平衡成本与质量
DEFAULT_STORYBOARD_THINKING = "enabled"  # 对应phase2生成分镜的配置
DEFAULT_STORYBOARD_REASONING_EFFORT = "high"  
DEFAULT_CHARACTER_PROMPT_THINKING = "enabled"  # 默认开启人物提示词思考，提升一致性
DEFAULT_CHARACTER_PROMPT_REASONING_EFFORT = "medium"  # 默认中等强度，保持稳定质量
DEFAULT_LOCATION_PROMPT_THINKING = "enabled"  # 默认开启场景提示词思考，降低偏差
DEFAULT_LOCATION_PROMPT_REASONING_EFFORT = "medium"  # 默认中等强度，平衡速度
DEFAULT_TTS_PROMPT_THINKING = "enabled"  # 默认开启解说词思考，提升表达质量
DEFAULT_TTS_PROMPT_REASONING_EFFORT = "medium"  # 默认中等强度，避免过慢
DEFAULT_FENJING_THINKING = "enabled"  # 默认开启分镜提示词思考，增强可用性
DEFAULT_FENJING_REASONING_EFFORT = "high"  # 默认高强度，优先保证提示词质量

DEFAULT_CHARACTER_HUMAN_IMAGE_SIZE = "1560x2560"  # 默认人物图像尺寸，兼顾清晰度与生成成本
DEFAULT_CHARACTER_BEAST_IMAGE_SIZE = "2800x1440"  # 默认兽类图像尺寸，适配横向构图

DEFAULT_VIDEO_PROMPT_THINKING = "enabled"  # 默认开启视频提示词思考，减少偏题
DEFAULT_VIDEO_PROMPT_REASONING_EFFORT = "high"  # 默认高强度，保障视频提示词质量
DEFAULT_VIDEO_MODEL_1_5_EP = DEFAULT_EMPTY_STRING  # 默认留空，避免调用错误模型端点
DEFAULT_VIDEO_MODEL_1_0_EP = DEFAULT_EMPTY_STRING  # 默认留空，避免调用错误模型端点
DEFAULT_VIDEO_RESOLUTION = "480p"  # 默认分辨率较低，控制成本
DEFAULT_VIDEO_RATIO = "9:16"  # 默认竖屏比例，贴合短视频场景
DEFAULT_VIDEO_MIN_DURATION_1_5 = 4.0  # 1.5 模型默认时长下限，避免过短
DEFAULT_VIDEO_MIN_DURATION_1_0 = 2.0  # 1.0 模型默认时长下限，避免过短

DEFAULT_IMAGE_MODEL_QPS = 3.0  # 默认温和限流，避免压垮图像模型
DEFAULT_IMAGE_MODEL_CONCURRENCY = 50  # 默认较高并发，提升吞吐
DEFAULT_VIDEO_TASK_QPS = 5.0  # 默认视频任务限流，保护下游资源
DEFAULT_VIDEO_AUDIO_DURATION_QPS = 5.0  # 默认音频时长估算限流，避免排队放大
DEFAULT_VIDEO_MODEL_1_5_QPS = 5.0  # 1.5 模型默认限流，保持稳定
DEFAULT_VIDEO_MODEL_1_5_CONCURRENCY = 10  # 1.5 模型默认并发，防止过载
DEFAULT_VIDEO_MODEL_1_0_QPS = 5.0  # 1.0 模型默认限流，保持稳定
DEFAULT_VIDEO_MODEL_1_0_CONCURRENCY = 10  # 1.0 模型默认并发，防止过载
DEFAULT_VIDEO_GENERATE_AUDIO = False  # 默认不自动生成音频，降低成本与依赖

# HTTP服务器配置
DEFAULT_SERVER_MAX_THREADS = 50  # 默认最大线程数，防止高并发时线程爆炸
DEFAULT_SERVER_HOST = "127.0.0.1"  # 默认监听本地地址，安全优先
DEFAULT_SERVER_PORT = 8086  # 默认服务端口

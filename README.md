# TTZ 剧本工作台 (Manju Web)

小说转视频全流程工作台，支持从小说文本自动生成分镜、角色/场景图片、语音和视频。

## 功能概览

- **自动分镜 (Auto Storyboard)** — 输入小说文本，LLM 自动提取角色、场景、分镜脚本
- **资产生成 (Visual Audio Assets)** — 自动生成角色立绘、场景背景、服装变装图、TTS 语音
- **分镜图生成 (Fenjing)** — 基于分镜脚本 + 角色/场景资产，批量生成分镜插图
- **视频合成 (Video)** — 将分镜图 + 语音合成为最终视频
- **项目管理** — 多项目支持、工作流状态追踪、任务队列管理

## 技术架构

```
Frontend (Vanilla JS)          Backend (Python HTTP Server)
┌─────────────────┐            ┌──────────────────────────┐
│  index.html     │  REST API  │  server.py               │
│  app.js         │ ◄────────► │  ├── handlers/           │
│  style.css      │            │  ├── services/           │
│  auth_config.*  │            │  │   ├── workflow_runtime/│
└─────────────────┘            │  │   │   ├── auto_storyboard │
                               │  │   │   ├── visual_audio_assets │
                               │  │   │   ├── fenjing     │
                               │  │   │   ├── video       │
                               │  │   │   └── provider_runtime │
                               │  ├── repositories/       │
                               │  └── config/             │
                               └──────────────────────────┘
                                          │
                               ┌──────────┴──────────┐
                               │  External Services   │
                               │  · Ark LLM API       │
                               │  · Seedream (图片)    │
                               │  · TTS (语音合成)     │
                               │  · TOS (对象存储)     │
                               └──────────────────────┘
```

## 快速开始

### 环境要求

- Python 3.10+
- Node.js (可选，仅开发前端时需要)

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置

1. 复制环境变量模板并填写：

```bash
cp .env.example .env
```

需要配置：
- `ARK_API_KEY` — Ark LLM API 密钥
- `TOS_ACCESS_KEY` / `TOS_SECRET_KEY` — TOS 对象存储凭证
- `TTS_URL` — TTS 服务地址

2. 或通过 Web 界面「配置」按钮设置

### 启动服务

```bash
cd manju_web
python -m backend.server
```

默认监听 `http://localhost:8080`

## 工作流程

```
小说文本
  │
  ▼
Phase 1: 自动分镜
  │  提取角色、场景、生成分镜脚本
  ▼
Phase 2: 资产生成
  │  角色立绘 → 场景背景 → 服装 → TTS 语音
  ▼
Phase 3: 分镜图生成
  │  结合角色+场景+分镜脚本生成插图
  ▼
Phase 4: 视频合成
  │  分镜图 + 语音 → 最终视频
  ▼
输出视频
```

## 项目结构

```
manju_web/
├── backend/
│   ├── server.py                 # HTTP 服务入口
│   ├── handlers/                 # 路由处理
│   │   ├── job_handler.py        # 任务管理 API
│   │   ├── project_handler.py    # 项目管理 API
│   │   ├── media_handler.py      # 媒体资源 API
│   │   └── config_handler.py     # 配置管理 API
│   ├── services/                 # 业务逻辑
│   │   ├── workflow_runtime/     # 核心工作流引擎
│   │   ├── workflow_service.py   # 工作流编排
│   │   ├── job_service.py        # 任务队列
│   │   └── status_service.py     # 状态管理
│   ├── repositories/             # 数据存储
│   └── config/                   # 配置文件
├── frontend/
│   ├── index.html                # 主页面
│   ├── app.js                    # 前端逻辑
│   └── style.css                 # 样式
└── README.md
```

## License

MIT

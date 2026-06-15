# 润笔阁

面向小说写作者的 AI 文本处理工具，帮助对 AI 生成的小说文本进行深度句式重构以过 AI 检测。输入卡密即可使用，按字数计费。

## 功能

- **过 AI 检测** — 对 AI 生成的文本进行深度句式重构，保留原意的同时降低 AI 特征，每次返回 8 个采样结果供挑选
- **逐词 diff** — 处理结果与原文逐词对比，增删内容分别以绿/红高亮，支持上下翻页浏览
- **卡密系统** — 用户凭卡密登录，系统按消耗字数扣费，额度用完即止
- **管理后台** — 查看用量统计、卡密列表、处理记录；在线生成卡密、配置 API

## 项目结构

```
├── main.py              # FastAPI 后端 (路由/卡密验证/LLM调用)
├── templates/
│   ├── login.html       # 卡密登录页
│   ├── rewrite.html     # 改写主页面 (diff 对比)
│   └── admin.html       # 管理后台 (侧边栏布局)
├── static/
│   └── app.js           # 前端交互
├── Dockerfile           # Docker 构建
├── deploy.sh            # 部署脚本
├── requirements.txt     # Python 依赖
└── novelforge.db        # SQLite (自动创建)
```

## 快速开始

### 方式一：直接运行

```bash
pip install -r requirements.txt
python main.py
```

### 方式二：Docker

```bash
chmod +x deploy.sh
./deploy.sh up           # 构建并启动
./deploy.sh down         # 清理容器和镜像
./deploy.sh restart      # 重新构建部署
```

## 配置

创建 `.env` 文件（容器部署时自动加载）：

```env
# 上游 LLM API
LLM_API_URL=https://your-api/v1/completions
LLM_API_KEY=your-key
LLM_MODEL=rewriter

# 管理密码 (默认 admin123)
ADMIN_PASSWORD=admin123

# 改写限制
MIN_WORDS=10             # 单次最少字数
SAMPLE_N=8               # 每次采样数
```

## 使用入口

| 页面 | 地址 |
|------|------|
| 登录 | `http://127.0.0.1:8000/login` |
| 处理页 | 登录后自动跳转 |
| 管理后台 | `http://127.0.0.1:8000/admin` |

## 测试卡密

| 卡密 | 额度 |
|------|------|
| `RUNBIGE-2024-TEST-001` | 100,000 字 |
| `RUNBIGE-2024-TEST-002` | 100,000 字 |
| `RUNBIGE-2024-VIP-003` | 100,000 字 |

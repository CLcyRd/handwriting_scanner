# 老电影艺术家手稿 AI 识别系统

## 环境准备

- Python 3.10+
- Gemini API Key

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置

在系统环境变量中设置：

```bash
GEMINI_API_KEY=你的密钥
```

## 启动

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

打开浏览器访问：

http://127.0.0.1:8010

## API

- POST /api/upload
- GET /api/recognize/{task_id}
- GET /api/download/{task_id}

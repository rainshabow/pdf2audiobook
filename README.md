# PDF 转语音

把 PDF 书籍转化为可听的有声书：解析章节 → dsv4-flash 口语化改写 → Qwen3-TTS 合成音频与字幕。

## 架构
- 后端：FastAPI（`backend/`），pymupdf 解析、LLM 改写、TTS 适配层、SQLite 任务库
- 前端：Vue 3 + Vite + TS（`frontend/`）
- 产物：`data/books/<book_id>/chapters/<chapter_id>/` 下 `speech.md`、`audio.wav`、`chapter.srt`、`chapter.vtt`、`segments.json`、`parts/`

## 快速开始
1. `cp .env.example .env`，填入 `OPENAI_API_KEY`（opencode dsv4-flash）；如需统一数据目录，可加 `DATA_DIR=D:\绝对路径\data`（默认是启动目录下的 `data/`）
2. 后端：`cd backend && python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000`
3. 前端：`cd frontend && npm install && npm run dev`，浏览器打开 `http://localhost:5173`
4. 上传 PDF → 解析章节 → 口语化改写 → 合成语音


## 一键启动脚本（Windows）
三个服务已封装为脚本（自动检测端口，已运行则跳过）：

```powershell
# 启动全部（qwen-tts-webui + 后端 + 前端）
.\scripts\start-all.ps1

# 只启动前端 / 只停止服务
.\scripts\start-all.ps1 -Frontend
.\scripts\start-all.ps1 -Stop
# 或
.\scripts\stop-all.ps1
```

- qwen-tts-webui 默认目录 D:\WorkSpace\qwen-tts-webui，可用 -QwenDir 覆盖
- 日志输出到 data/logs/（qwen/backend/frontend 各自 out/err 文件）
- 服务未安装依赖时会提示对应的安装命令

## 接入本机 qwen-tts-webui（需 NVIDIA GPU）

1. 按 https://github.com/licyk/qwen-tts-webui 安装并启动（API-only）：`python launch.py --nowebui --server-name 0.0.0.0 --server-port 7860`
2. 前端「设置」将引擎切到 `qwen_webui`，首次合成会自动下载模型

## 测试
- 后端：`cd backend && python -m pytest`
- 前端：`cd frontend && npm run test`

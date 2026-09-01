# PDF 转语音

把 PDF 书籍转化为可听的有声书：解析章节 → dsv4-flash 口语化改写 → Qwen3-TTS 合成音频与字幕。

## 架构
- 后端：FastAPI（`backend/`），pymupdf 解析、LLM 改写、TTS 适配层、SQLite 任务库
- 前端：Vue 3 + Vite + TS（`frontend/`）
- 产物：`data/books/<book_id>/chapters/<chapter_id>/` 下 `speech.md`、`audio.wav`、`chapter.srt`、`chapter.vtt`、`segments.json`、`parts/`

## 快速开始
1. `cp .env.example .env`，填入 `OPENAI_API_KEY`（opencode dsv4-flash）
2. 后端：`cd backend && python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000`
3. 前端：`cd frontend && npm install && npm run dev`，浏览器打开 `http://localhost:5173`
4. 上传 PDF → 解析章节 → 口语化改写 → 合成语音

## 接入本机 qwen-tts-webui（需 NVIDIA GPU）
1. 按 https://github.com/licyk/qwen-tts-webui 安装并启动：`python launch.py --api --server-name 0.0.0.0 --server-port 7860`
2. 前端「设置」将引擎切到 `qwen_webui`，首次合成会自动下载模型

## 测试
- 后端：`cd backend && python -m pytest`
- 前端：`cd frontend && npm run test`

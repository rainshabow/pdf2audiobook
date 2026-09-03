# PDF 转语音

把 PDF 书籍转化为可听的有声书：解析章节 → deepseek-v4-flash 口语化改写 → Qwen3-TTS 合成音频与字幕。

## 架构
- 后端：FastAPI（`backend/`），pymupdf 解析、LLM 改写、TTS 适配层、SQLite 任务库
- 前端：Vue 3 + Vite + TS（`frontend/`）
- 产物：`data/books/<book_id>/chapters/<chapter_id>/` 下 `speech.md`、`audio.wav`、`chapter.srt`、`chapter.vtt`、`segments.json`、`parts/`

## 快速开始
1. `cp .env.example .env`，填入 `OPENAI_API_KEY`（opencode deepseek-v4-flash）；如需统一数据目录，可加 `DATA_DIR=D:\绝对路径\data`（默认是启动目录下的 `data/`）
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

## 接入云端 MiMo-TTS 2.5（无需 GPU）

1. 在 `.env` 配置 `MIMO_API_KEY=sk-...`（`MIMO_BASE_URL` 默认 `https://api.xiaomimimo.com/v1`，一般无需改动）
2. 前端「设置」将引擎切到 `mimo（云端 MiMo-TTS 2.5）`，保存后即可合成：
   - 模型：`mimo-v2.5-tts`（预置音色）、`mimo-v2.5-tts-voicedesign`（用描述生成音色，朗读指示即设计描述）
   - 合成模式选 Voice Clone 时自动使用 `mimo-v2.5-tts-voiceclone`，需上传参考音频（wav/mp3）
   - 预置音色：`mimo_default`、冰糖、茉莉、苏打、白桦、Mia、Chloe、Milo、Dean
   - 语速仍由应用按「固化语速」后处理（默认 1.25 倍）
   - 云端接口按次计费，速度与 GPU 无关，可作为本机 qwen 引擎的换源方案

## 并发模型
- 改写（LLM/CPU）与合成（GPU）使用**双通道并行**：两类任务可同时进行，互不阻塞
- 同类型任务仍串行（改写之间、合成之间），避免资源争抢；改写任务内部按并发上限并行调用 LLM，合成任务内部也按「合成并发上限」并行提交 TTS 批次

## 效率与音色设置（前端「设置」页）
- 改写并发上限：默认 20，可在书籍页/章节页开始改写时调整
- 默认每个分段都经 LLM 改写（括号/小标题/序号等朗读效果更佳）；纯文本透传已停用（可经代码开关 passthrough_plain 开启）
- 合成批处理：分句合并 + 一次请求提交多句（`segment_gen`），减少请求开销
- 合成并发上限：默认 2（设置页/书籍页/章节页可调）。本机 qwen 建议 1–2；云端 mimo 每次请求单句，可调大（如 4–8）显著提速
- 合成前默认文本预处理：独立全大写缩写拆为逐字母拼读（`LLM → L L M`、`ID → I D`），只影响送入 TTS 的文本；`speech.md` 与字幕保持原文
- 基础语速：默认 1.25 倍（固化进音频，字幕同步换算）
- 合成模式：CustomVoice（选声音）或 Voice Clone（上传参考音频克隆音色，首次使用会自动下载 Base 模型）
- qwen / mimo 每个预置音色旁均有「试听」按钮，试听文本固定为“你好，世界”
- 语气一致性：默认朗读指示为“平稳、一致、中性稳定”，配合批量合成减少分句间情绪波动

## 测试
- 后端：`cd backend && python -m pytest`
- 前端：`cd frontend && npm run test`

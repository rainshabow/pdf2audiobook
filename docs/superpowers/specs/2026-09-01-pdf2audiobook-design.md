# PDF 转语音应用 — 设计文档

- 日期：2026-09-01
- 状态：已确认（用户已批准整体设计，含字幕补充）
- 仓库：D:\WorkSpace\PDF转语音（新初始化）

## 1. 背景与目标

把 PDF 版本的书籍转化为可听的语音，核心诉求：

1. **高保真 + 口语化改写**：在保留原文信息（数字、术语、专有名词）的前提下，对依赖视觉排版呈现的内容（表格、列表、图注、公式、交叉引用等）做简单改写，符合口语朗读习惯。
2. **按大章节自适应输出**：自动切分并合并成"大章节"，每章输出一个完整音频。
3. **人工可维护的 MD 与易重建的单章节语音**：`speech.md` 是可编辑的普通文件；改文本、换声音、调速后，可只重建受影响章节，且已合成分句增量复用。
4. **AI 语音合成**：技术选型与模型选型参考 https://github.com/licyk/qwen-tts-webui（Qwen3-TTS 系列），支持**换源（不同声音/发言人）**与**调速**。
5. **Web 界面、前后端分离**：浏览器前端 + 独立后端 API。

### 字幕要求（用户补充确认）

语音必须配有字幕：每章输出 `.srt` 与 `.vtt` 字幕文件，与音频同步；重建音频时字幕随音频一起重建。

## 2. 已确认决策

| 项 | 决策 |
|---|---|
| TTS 引擎 | 本机部署 qwen-tts-webui（Qwen3-TTS），RTX 5060 Laptop 8GB 显存（用户手动开启 GPU）；开发阶段用可替换的测试适配器跑通全流程 |
| LLM 改写 | opencode 的 `dsv4-flash`，OpenAI 兼容接口，Base URL `https://opencode.ai/zen/go/v1` |
| 密钥管理 | API Key 存于 `.env`，`.env` 加入 `.gitignore` 不上传；提供 `.env.example` 占位模板 |
| 前端 | Vue 3 + Vite + TypeScript |
| 后端 | Python 3.13 + FastAPI（进程内 asyncio 任务队列） |
| 语言 | 中文为主，兼容中英混排；Qwen3-TTS 自动检测语言 |

## 3. 总体架构

```
浏览器（Vue 3 前端）
   │ REST API + 轮询进度
   ▼
FastAPI 后端
   ├─ PDF 解析 / 章节切分（pymupdf）
   ├─ LLM 口语化改写（dsv4-flash，OpenAI 兼容）
   ├─ 任务队列 / 作业管理（进程内 asyncio，TTS 串行）
   └─ TTS 引擎适配层（qwen-tts-webui HTTP / 测试引擎）
          │
          ▼
本机 qwen-tts-webui（Qwen3-TTS，5060 GPU）
```

- 后端为单进程 FastAPI 应用，任务在进程内排队执行；TTS 引擎同一时间只处理一个任务，故合成任务天然串行。
- 不使用 Celery/Redis：本机单用户场景，进程内队列足够，降低部署与运维复杂度。
- 前后端分离：后端只暴露 JSON API 与静态资源服务；前端独立构建。

## 4. 数据模型与文件结构

每本书一个目录，所有产物均为普通文件，便于人工维护、备份与迁移：

```
data/books/<book_id>/
  source.pdf
  meta.json                 # 书名/作者/页数/TOC/解析状态
  chapters.json             # 章节切分结果：大章节列表、页码范围、标题层级
  chapters/<chapter_id>/
    source.md               # 抽取的原始正文（对照参考）
    speech.md               # ★ 口语化改写结果（人工可维护）
    segments.json           # ★ 分句清单 + 每句时间轴（TTS 合成时记录起止）
    audio.wav               # ★ 整章合成音频
    chapter.srt             # ★ 字幕文件（SRT）
    chapter.vtt             # ★ 字幕文件（VTT，网页播放器原生支持）
    parts/                  # 分句音频（重建/换源时增量复用）
    status.json             # 章节状态（解析/改写/合成 阶段与结果）
  settings.json             # 每本书的引擎/声音/语速设置快照
data/jobs.db                # SQLite：任务进度/历史/设置快照
```

**重建语义**：修改 `speech.md`、切换声音、固化语速，只重建对应章节；分句音频与 `segments.json` 中记录每句内容哈希，文本未变的分句直接复用（增量合成）。

### meta.json / chapters.json 关键字段

```jsonc
// meta.json
{ "book_id": "...", "title": "...", "author": "...", "page_count": 599,
  "toc": [ { "level": 1, "title": "I 基础", "page": 38 } ], "status": "parsed" }

// chapters.json
{ "chapters": [
    { "id": "ch-001", "title": "第1章 LLM 架构与优化方法", "level": 2,
      "page_start": 39, "page_end": 58, "char_count": 12000 } ] }
```

## 5. PDF 解析与章节切分

- 使用 **pymupdf** 抽取文本块（含字号、加粗、位置、表格、图片等布局信息）。
- 章节来源优先级：
  1. PDF 内嵌书签/大纲（`doc.get_toc()`），示例 PDF 有完整目录；
  2. 无书签时按字号/加粗/编号模式做标题检测。
- **自适应大章节合并规则**（可配置）：
  - 以顶层章节（Part/Chapter）为基本单元；
  - 目标每章约 10–30 分钟音频（约 5000–15000 字）：太长的章节按二级标题拆分为多个大章节；太短的相邻章节合并。
  - 阈值可在设置中调整。
- 抽取阶段即剔除页眉/页脚/页码/目录页等排版噪音，保留图注、表格、列表、代码块、公式的结构化标注（写进 `source.md` 与 LLM 输入）。
- 扫描版 PDF（无文本层）不在 MVP 范围内，架构预留 OCR 接入点。

## 6. 口语化改写（dsv4-flash）

- 输入：按章节抽取的结构化文本（段落/表格/列表/图注/代码块/公式分类标注）。
- 分节调用 LLM：每节约 2000–4000 字，低温度（0.2–0.3），失败指数退避重试。
- 提示词要点（系统提示固定、按中文书籍优化）：
  - **高保真**：数字、日期、术语、专有名词、代码标识符原样保留，不得遗漏或总结；
  - 表格 → 陈述句（"X 为……，Y 为……"）；
  - 列表 → "第一/第二/首先/其次" 等口语衔接；
  - 图注 → "如图 X 所示，……"；
  - 公式 → 读出式表达（如"f 对 x 的导数等于……"）；
  - 交叉引用 → "如第 X 章所述"；
  - 清除排版噪音；输出 Markdown（标题层级与章节结构保持一致）。
- **断点续跑**：每节结果即时写入 `speech.md` 并记录进度；中断后可继续未完成的节，已完成的节不重复调用。
- 纯排版噪音在抽取阶段已剔除；LLM 只做"改写"，不做"提炼/总结"，保证信息高保真。

## 7. TTS 引擎层

统一适配器接口（`app/services/tts/base.py`）：

```python
class TTSAdapter(ABC):
    async def list_models(self) -> list[ModelInfo]: ...
    async def list_speakers(self) -> list[SpeakerInfo]: ...
    async def synthesize(self, text: str, *, voice: str, speed: float,
                         language: str | None, instruct: str | None) -> AudioResult: ...
# AudioResult: bytes（wav）+ duration_seconds（合成实际时长）
```

### 引擎实现

| 适配器 | 用途 | 说明 |
|---|---|---|
| `qwen_webui` | 正式引擎 | 调用本机 qwen-tts-webui：`GET /qwenapi/v1/models|speakers|languages`、`POST /qwenapi/v1/custom-voice`（CustomVoice 多发言人=换源）、`/voice-design`、`/voice-clone`（预留）；返回 Base64 WAV；`POST /interrupt` 取消 |
| `mock` | 开发/测试 | 根据文本生成静音或提示音 WAV，全流程不依赖 GPU 可跑通 |
| `edge_tts`（可选） | 免费备选 | 作为无 GPU 时的真实语音备选，架构上即插即用 |

- **分句合成**：后端按段落/句子切分 `speech.md` 为 segments，逐句调用引擎并记录每句实际时长（`segments.json`），最后拼接为 `audio.wav`。
- **换源**：切换 CustomVoice 的 speaker / VoiceDesign 描述 / 克隆音色 → 重建章节音频。
- **调速双通道**：
  1. 前端播放器实时倍速（0.5–2.0×），不重新合成；
  2. 重建时可选"固化语速"：用 ffmpeg atempo 变速后写入 `audio.wav`，字幕时间轴按倍率换算。
- **增量复用**：`segments.json` 记录每句文本哈希；重建时文本未变的句子直接复用 `parts/` 中的音频与时长，只合成变化句。

## 8. 字幕（用户补充需求）

- 数据源：`segments.json`（每句文本 + 起止时间，拼接时累计得到绝对时间轴）。
- 产物：每章生成 `chapter.srt` 与 `chapter.vtt` 两个普通文本文件，与 `audio.wav` 同目录。
- 同步机制：字幕时间来自**合成实际时长**的累计，不依赖语音识别，天然同步。
- 人工可维护：`chapter.srt/.vtt` 可直接编辑；也可在"章节页"编辑字幕文本后重新生成。
- 固化语速：字幕时间轴按 atempo 倍率换算后重新生成。
- 前端播放器使用 VTT 实现当前句高亮与字幕显示。

## 9. 前端设计（Vue 3 + Vite + TS）

| 页面 | 功能 |
|---|---|
| 书架 | PDF 上传、书籍列表、删除 |
| 书籍详情 | 章节树 + 每章状态/时长 + 一键"解析/改写/合成" |
| 章节页 | Markdown 编辑器 + 预览（`speech.md`，改动即存）；音频播放器（语速、声音切换、**字幕同步高亮**）；"重建本章音频" |
| 任务中心 | 队列进度、取消、失败重试 |
| 设置 | 引擎选择（mock/qwen-webui/edge-tts）、模型、声音、语速、LLM 配置 |

- 技术：Vue 3 + Vite + TS + Vue Router + Pinia；UI 组件库建议 Naive UI（或 Element Plus）；Markdown 编辑用 CodeMirror 6；播放器用原生 `<audio>` + `<track>`/自定义字幕渲染。
- API 客户端统一封装（axios），进度用轻量轮询（MVP），后续可升级 SSE。

## 10. 后端 API 设计（FastAPI）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/books` | 上传 PDF，创建书籍记录 |
| GET | `/api/books` | 书籍列表 |
| GET | `/api/books/{id}` | 书籍详情（含章节树与状态） |
| DELETE | `/api/books/{id}` | 删除书籍（含全部产物） |
| POST | `/api/books/{id}/parse` | 启动解析/章节切分任务 |
| POST | `/api/books/{id}/rewrite` | 启动全书记口语化改写任务 |
| POST | `/api/books/{id}/synthesize` | 启动全书合成任务 |
| GET | `/api/books/{id}/chapters/{ch}/speech.md` | 读取 `speech.md` |
| PUT | `/api/books/{id}/chapters/{ch}/speech.md` | 保存 `speech.md` |
| POST | `/api/books/{id}/chapters/{ch}/rebuild` | 重建本章音频+字幕 |
| GET | `/api/books/{id}/chapters/{ch}/audio` | 音频流 |
| GET | `/api/books/{id}/chapters/{ch}/chapter.vtt` | 字幕文件 |
| GET | `/api/jobs` | 任务列表/状态 |
| POST | `/api/jobs/{id}/cancel` | 取消任务（TTS 调用 /interrupt） |
| GET | `/api/settings` / PUT | 读取/保存设置（引擎、模型、声音、语速） |
| GET | `/api/tts/models` `/api/tts/speakers` | 动态获取引擎可用模型/声音 |

## 11. 任务管理

- 任务类型：`parse / rewrite / synthesize / rebuild`。
- 任务状态机：`pending → running → done | failed | cancelled`，记录进度、错误信息、设置快照。
- 队列：进程内 asyncio 队列；合成任务全局串行（引擎单任务锁）。
- 取消：调用 `POST /qwenapi/v1/interrupt`，保留已完成分句，可续跑。
- 持久化：SQLite `jobs.db` 保存任务历史与进度，后端重启后可查看/续跑。

## 12. 错误处理

- PDF：加密/损坏/无文本层 → 明确错误提示；无文本层提示需 OCR（预留）。
- LLM：限流/超时 → 指数退避重试；单节失败不阻塞整章，记录错误并支持重试该节。
- TTS：引擎未启动/显存不足/模型未下载 → 明确错误码与提示；分句失败可单独重试。
- 磁盘：空间不足 → 停止任务并提示。
- 所有错误在前端任务中心可见、可重试；任务中断不破坏已生成产物。

## 13. 配置与安全

- `.env`（不上传 git）：`OPENAI_BASE_URL`、`OPENAI_API_KEY`、`LLM_MODEL=dsv4-flash`、`TTS_ENGINE`、`TTS_API_URL`、`TTS_MODEL`、`TTS_SPEAKER`、`TTS_SPEED` 等。
- `.env.example`（上传 git）：同键名占位模板。
- `.gitignore`：`.env`、`data/`、`__pycache__/`、`.venv/`、`node_modules/`、`dist/` 等。
- 设置可经 UI 读写（`settings.json`），敏感值只存 `.env`。

## 14. 测试策略

- 后端 pytest：
  - `pdf_extractor`：示例 PDF（agentic-ai-guide-zh）解析正确性（页数、TOC、章节）；
  - `segmenter`：TOC 合并/拆分规则、无 TOC 字号检测；
  - `rewriter`：mock LLM（OpenAI 兼容 HTTP 模拟），验证分节、断点续跑、提示词组装；
  - `tts` 适配器：httpx MockTransport 模拟 qwen-webui API；mock 引擎端到端；
  - `job_manager`：队列、取消、续跑；API 集成测试。
- 前端 Vitest：工具函数、状态管理、API client。
- 全流程验收（手动）：上传示例 PDF → 解析 → 改写（真实 dsv4-flash）→ mock 合成 → 播放/字幕；GPU 开启后切换 qwen-webui 真引擎验收。

## 15. MVP 范围与非目标

**MVP 包含**：单用户本机应用；PDF 上传与解析；TOC/字号自适应章节切分；dsv4-flash 口语化改写（可断点）；分句合成 + 增量复用；整章 `audio.wav` + `chapter.srt/.vtt`；Markdown 编辑与单章重建；播放器（倍速/换声/字幕高亮）；任务中心；引擎切换（mock/qwen-webui）。

**非目标（后续迭代）**：OCR（扫描版）、用户认证/多用户、流式合成、声音克隆 UI（接口预留）、多语言 UI、移动端适配、SSE 实时进度（可用轮询替代）。

## 16. 实施顺序（概览）

1. 仓库初始化（git、.gitignore、.env.example、目录骨架）
2. 后端：存储层与文件结构 → PDF 解析/切分 → LLM 改写 → TTS 适配层（mock 先行）→ 字幕/音频拼接 → API
3. 前端：脚手架 → 书架/书籍详情 → 章节编辑与播放 → 任务中心 → 设置
4. 集成与验收：示例 PDF 全流程；GPU 开启后接入 qwen-tts-webui 真机验收

> 详细分步实施计划由 writing-plans 技能产出。

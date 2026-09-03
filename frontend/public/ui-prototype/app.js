/* ============ UI 原型逻辑（纯前端模拟，不连后端） ============ */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const STATE = { view: "books", bookId: "agent", chIdx: 1, playing: false, playingVoice: null };

const BOOKS = [
  { id: "agent", title: "智能体 AI 指南", sub: "Agentic AI Guide · 中文版", pages: 599, chapters: 32, status: "synth", progress: 68, dur: "1:04:12" },
  { id: "design", title: "Agent 系统设计实战", sub: "从工具到多智能体编排", pages: 320, chapters: 12, status: "rewrite", progress: 10, dur: "0:00:00" },
];

const CHAPTERS = [
  { title: "第 1–3 章 · 智能体 AI 导论与基础", pages: "1–86", chars: "6.8 万字", status: "done", dur: "1:02:34", done: 100 },
  { title: "第 4–5 章 · LLM 架构与优化", pages: "87–152", chars: "7.5 万字", status: "run", dur: "42:10", done: 68 },
  { title: "第 6 章 · 面向 LLM 的强化学习", pages: "153–210", chars: "5.0 万字", status: "rewritten", dur: null, done: 100 },
  { title: "第 7 章 · 检索增强生成（RAG）", pages: "211–268", chars: "5.3 万字", status: "pending", dur: null, done: 0 },
  { title: "第 8–9 章 · 评估与基准", pages: "269–330", chars: "6.1 万字", status: "fail", dur: null, done: 0 },
];

const DOC = [
  "本章先回答一个基础问题：<b class='hl'>LLM</b> 为什么能成为智能体的大脑？我们不会停留在“大模型很强”这种结论上，而是逐步拆解它的工作机制。",
  "近年来，<b class='hl'>MoE</b> 与 <b class='hl'>vLLM</b> 这类工程创新，让推理吞吐量提升了一个数量级；与此同时，<b class='hl'>RAG</b> 把外部知识接入对话，使答案更可核查。",
  "请先填写你的 <b class='hl'>ID</b>，系统会用它关联任务记录；调用 <b class='hl'>API</b> 时注意检查 <b class='hl'>URL</b> 是否正确。",
];

const JOBS = [
  { id: "j1", type: "synth", typeText: "合成", book: "智能体 AI 指南", chapter: "第 4–5 章 · LLM 架构与优化", progress: 68, status: "run", err: null },
  { id: "j2", type: "rewrite", typeText: "改写", book: "智能体 AI 指南", chapter: "第 7 章 · 检索增强生成（RAG）", progress: 23, status: "run", err: null },
  { id: "h1", type: "parse", typeText: "解析", book: "智能体 AI 指南", chapter: "", progress: 100, status: "done", err: null },
  { id: "h2", type: "synth", typeText: "合成", book: "智能体 AI 指南", chapter: "第 1–3 章", progress: 100, status: "done", err: null },
  { id: "h3", type: "synth", typeText: "合成", book: "智能体 AI 指南", chapter: "第 8–9 章", progress: 12, status: "fail", err: "qwen 引擎连接超时，请重试" },
];

const MIMO_VOICES = ["mimo_default", "冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean"];
const QWEN_VOICES = ["vivian", "serena", "adam", "小雅", "默认"];

const STATUS = {
  done: ["已完成", "badge ok"], run: ["合成中", "badge run"], rewritten: ["待合成", "badge wait"],
  pending: ["待改写", "badge wait"], fail: ["失败", "badge err"], partial: ["部分完成", "badge ok"],
};

/* ---------------- Toast ---------------- */
function toast(msg, ok = true) {
  const box = $("#toast");
  const t = document.createElement("div");
  t.className = "toast" + (ok ? " ok" : "");
  t.innerHTML = (ok ? "✓ " : "✕ ") + msg;
  box.appendChild(t);
  setTimeout(() => { t.style.transition = ".3s"; t.style.opacity = "0"; t.style.transform = "translateY(8px)"; setTimeout(() => t.remove(), 300); }, 2200);
}

/* ---------------- Navigation ---------------- */
const VIEW_TITLE = { books: "书架", jobs: "任务中心", settings: "设置" };

function showView(name) {
  STATE.view = name;
  $$(".view").forEach(v => v.classList.remove("active"));
  $(`#view-${name}`).classList.add("active");
  $$(".nav-item").forEach(n => n.classList.toggle("active", n.dataset.nav === name));
  updateCrumbs();
  if (name === "books") renderBooks();
  if (name === "jobs") renderJobs();
  if (name === "settings") renderSettings();
}

function updateCrumbs() {
  const c = $("#crumbs");
  const parts = [];
  if (STATE.view === "book" || STATE.view === "chapter") {
    parts.push({ label: "书架", click: () => showView("books") });
    const book = BOOKS.find(b => b.id === STATE.bookId);
    parts.push({ label: book.title, click: () => openBook(book.id) });
  }
  if (STATE.view === "chapter") {
    const ch = CHAPTERS[STATE.chIdx];
    parts.push({ label: ch.title, current: true });
  } else if (STATE.view === "book") {
    parts.push({ label: "工作台", current: true });
  } else {
    parts.push({ label: VIEW_TITLE[STATE.view], current: true });
  }
  c.innerHTML = parts.map((p, i) => {
    const sep = i ? '<span class="crumb-sep">›</span>' : "";
    return sep + (p.current ? `<span class="crumb current">${p.label}</span>` : `<span class="crumb link">${p.label}</span>`);
  }).join("");
  bindCrumbs(c, parts);
}

function bindCrumbs(c, parts) {
  let idx = 0;
  $$(".crumb.link", c).forEach(el => { const p = parts[idx]; el.onclick = p.click; idx++; });
}

/* ---------------- 书架 ---------------- */
function renderBooks() {
  const grid = $("#booksGrid");
  grid.innerHTML = BOOKS.map((b, i) => {
    const st = b.status === "synth" ? ["合成中", "badge run"] : b.status === "rewrite" ? ["改写中", "badge run"] : ["已完成", "badge ok"];
    const ring = b.status === "rewrite" ? 10 : 68;
    return `<div class="book-card" style="animation-delay:${i * 60}ms" onclick="openBook('${b.id}')">
      <div class="book-cover">
        <span style="font-size:26px;font-weight:800;opacity:.95;text-shadow:0 2px 10px rgba(0,0,0,.15)">${b.title.slice(0,1)}</span>
        <span style="margin-left:8px;font-size:13px;opacity:.9">${b.chapters} 章</span>
        <div class="prog-ring" style="background:conic-gradient(#059669 ${ring*3.6}deg,#E8F2EE 0deg)"><span style="background:#fff;width:32px;height:32px;border-radius:50%;display:grid;place-items:center">${ring}%</span></div>
      </div>
      <div class="book-body">
        <div class="book-title">${b.title}</div>
        <div class="book-meta"><span>${b.pages} 页</span><span>${b.chapters} 章</span><span>已合成 ${b.dur}</span></div>
        <div class="badges"><span class="badge ${st[1]}"><span class="bdot"></span>${st[0]}</span></div>
      </div>
    </div>`;
  }).join("");
}

function simulateUpload() {
  toast("PDF 已加入队列：解析章节中…");
}

/* ---------------- 书籍工作台 ---------------- */
function openBook(id) {
  STATE.bookId = id;
  STATE.view = "book";
  renderBookDetail();
  showView("book");
}

function renderBookDetail() {
  const b = BOOKS.find(x => x.id === STATE.bookId);
  const steps = [
    { n: "1", txt: "解析章节", done: true },
    { n: "2", txt: "口语化改写", done: true },
    { n: "3", txt: "分章合成", done: false, now: true },
  ];
  const rows = CHAPTERS.map((ch, i) => {
    const st = STATUS[ch.status];
    const run = ch.status === "run";
    return `<div class="ch-row" style="animation-delay:${i*40}ms" onclick="openChapter(${i})">
      ${run ? '<span class="eq"><i></i><i></i><i></i><i></i></span>' : `<span class="ch-num" style="width:34px;height:34px;border-radius:10px;background:${ch.status==='done'?'var(--green-100)':'#EDF2F0'};display:grid;place-items:center;font-weight:700;color:${ch.status==='done'?'var(--green-700)':'var(--muted)'}">${i+1}</span>`}
      <div style="flex:1;min-width:0">
        <div class="ch-title">${ch.title}</div>
        <div class="ch-meta">p${ch.pages} · ${ch.chars}</div>
      </div>
      ${run ? `<div class="progress row-progress"><div class="bar" style="width:${ch.done}%"></div></div><span class="pct">${ch.done}%</span>` : ch.dur ? `<span class="ch-meta" style="font-variant-numeric:tabular-nums">${ch.dur}</span>` : ""}
      <span class="badge ${st[1]}"><span class="bdot"></span>${st[0]}</span>
      <div class="ch-actions">
        ${ch.status==='done' ? `<button class="btn btn-soft btn-sm" onclick="event.stopPropagation();toast('开始播放本章')">▶ 播放</button>` : `<button class="btn btn-soft btn-sm" onclick="event.stopPropagation();toast('已加入合成队列')">合成</button>`}
        <button class="btn btn-ghost btn-sm" onclick="event.stopPropagation();openChapter(${i})">编辑</button>
      </div>
    </div>`;
  }).join("");

  $("#bookDetail").innerHTML = `
    <div class="page-head">
      <div>
        <h1>${b.title}</h1>
        <div class="sub">${b.sub} · ${b.pages} 页 · ${b.chapters} 章</div>
      </div>
      <div style="display:flex;gap:10px">
        <button class="btn btn-ghost" onclick="toast('打开原文目录')">目录</button>
        <button class="btn btn-primary" onclick="toast('全部合成已开始，可在任务中心查看')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>继续合成
        </button>
      </div>
    </div>
    <div class="stepper">
      ${steps.map(s => `<div class="step ${s.done?'done':''} ${s.now?'now':''}"><span class="step-num">${s.done?'✓':s.n}</span><span class="step-txt">${s.txt}</span></div><div class="step-line"><span class="fill"></span></div>`).join("")}
    </div>
    <div class="section-title">章节 <span class="muted" style="font-weight:400;font-size:13px">· 点击整行进入章节工作台</span></div>
    <div class="ch-list">${rows}</div>`;
}

/* ---------------- 章节工作台 ---------------- */
function openChapter(idx) {
  STATE.chIdx = idx;
  STATE.view = "chapter";
  renderChapter();
  showView("chapter");
}

function renderChapter() {
  const ch = CHAPTERS[STATE.chIdx];
  const prev = STATE.chIdx > 0;
  const next = STATE.chIdx < CHAPTERS.length - 1;
  const done = ch.status === "done";
  const docHtml = DOC.map(p => `<p>${p}</p>`).join("");
  $("#chapterWB").innerHTML = `
    <div class="page-head">
      <div><h1 style="font-size:20px">${ch.title}</h1>
        <div class="sub">第 ${STATE.chIdx+1} / ${CHAPTERS.length} 章 · p${ch.pages} · ${ch.chars} · 朗读版 1.25×</div>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-ghost btn-sm" onclick="toast('已还原为原文，可重新改写')">还原原文</button>
        <button class="btn btn-soft btn-sm" onclick="toast('改写任务已开始')">改写本章</button>
        <button class="btn btn-primary btn-sm" onclick="toast('合成本章已开始')">合成本章</button>
      </div>
    </div>
    <div class="wb">
      <div class="panel">
        <div class="panel-title">朗读文本
          <span class="tabs"><button class="tab active">朗读</button><button class="tab">原文</button></span>
        </div>
        <div class="docbox">${docHtml}</div>
        <div class="editor-actions">
          <button class="btn btn-ghost btn-sm" onclick="toast('已保存 speech.md')">保存文本</button>
          <span class="badge ok" style="margin-left:4px"><span class="bdot"></span>已自动保存</span>
          <span class="kbd" style="margin-left:auto">Ctrl+S</span>
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:14px">
        <div class="panel">
          <div class="panel-title">播放器 <span class="badge ok"><span class="bdot"></span>第 ${STATE.chIdx+1} 章</span></div>
          <div class="player-box">
            <div class="audio-disc ${STATE.playing?'':'paused'}" id="disc" style="margin:4px auto 10px">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
            </div>
            <div class="cue" id="cue"><b>LLM</b> 为什么能成为智能体的大脑？</div>
            <div class="range-row"><span>00:12</span><input type="range" value="18" max="100"><span>${ch.dur||"0:42:10"}</span></div>
            <div class="speed-row"><span class="muted" style="font-size:12px">倍速</span>
              <div class="seg-select"><select><option>1.0×</option><option selected>1.25×</option><option>1.5×</option><option>2.0×</option></select>
              <button class="icon-btn" style="width:34px;height:34px" onclick="togglePlay()"><span id="playIcon">⏸</span></button></div>
            </div>
          </div>
        </div>
        <div class="panel">
          <div class="panel-title">语音克隆 <span class="badge run" style="font-weight:400">可选</span></div>
          <div class="muted" style="font-size:12px;line-height:1.7">已选用音色 <b style="color:var(--green-700)">茉莉</b>；克隆模式下自动使用 <b>voiceclone</b> 并上传参考音频。</div>
          <div style="margin-top:12px"><button class="btn btn-ghost btn-sm" onclick="toast('打开音色试听面板')">更换音色</button></div>
        </div>
      </div>
    </div>
    <div class="ch-nav">
      <button class="btn btn-ghost" ${prev?"":"disabled"} onclick="openChapter(${STATE.chIdx-1})">← 上一章</button>
      <span class="muted" style="font-size:12px;align-self:center">使用 <span class="kbd">←</span> <span class="kbd">→</span> 快速翻章</span>
      <button class="btn btn-ghost" ${next?"":"disabled"} onclick="openChapter(${STATE.chIdx+1})">下一章 →</button>
    </div>`;
  if (STATE.playing) startCueCycle();
}

function togglePlay() {
  STATE.playing = !STATE.playing;
  const disc = $("#disc"); const icon = $("#playIcon");
  if (disc) disc.classList.toggle("paused", !STATE.playing);
  if (icon) icon.textContent = STATE.playing ? "⏸" : "▶";
  if (STATE.playing) startCueCycle(); else stopCueCycle();
  toast(STATE.playing ? "正在播放" : "已暂停");
}
let cueTimer = null, cueIdx = 0;
function startCueCycle() {
  stopCueCycle();
  cueIdx = 0;
  cueTimer = setInterval(() => {
    const cue = $("#cue"); if (!cue) return;
    const texts = ["<b>LLM</b> 为什么能成为智能体的大脑？", "MoE 与 <b>vLLM</b> 让推理吞吐量大幅提升", "请先填写你的 <b>ID</b>，再调用 <b>API</b>"];
    cue.innerHTML = texts[cueIdx % texts.length]; cueIdx++;
  }, 2600);
}
function stopCueCycle() { if (cueTimer) { clearInterval(cueTimer); cueTimer = null; } }

/* ---------------- 任务中心 ---------------- */
function renderJobs(manual = false) {
  const run = JOBS.filter(j => j.status === "run");
  const hist = JOBS.filter(j => j.status !== "run");
  const card = (j) => {
    const isRun = j.status === "run";
    return `<div class="job-card" style="animation:cardIn .3s var(--ease) both" ${isRun?"onclick=\"goJob('"+j.id+"')\"":""}>
      <div class="job-type ${j.type}">${j.type==='parse'?'解':j.type==='rewrite'?'改':'合'}</div>
      <div class="job-main">
        <div class="job-title">${j.typeText} · ${j.book}${j.chapter ? ` <span class="muted" style="font-weight:400">› ${j.chapter}</span>` : ""}
          <span class="badge ${isRun?'run':j.status==='fail'?'err':'ok'}"><span class="bdot"></span>${isRun?'进行中':j.status==='fail'?'失败':'完成'}</span></div>
        <div class="job-sub">${j.err || (j.type==='synth' ? "TTS 通道 · MiMo 云端" : "LLM 通道 · 并发 20")}</div>
      </div>
      <div class="job-right">
        ${isRun ? `<div class="progress" style="width:150px"><div class="bar" style="width:${j.progress}%"></div></div><span class="pct">${j.progress}%</span>
          <button class="btn btn-danger-ghost btn-sm" onclick="event.stopPropagation();toast('任务已取消',false)">取消</button>` : `<span class="ch-meta">${j.status==='fail'?'点击可重试':''}</span>`}
      </div>
    </div>`;
  };
  $("#jobsContent").innerHTML = `
    ${run.length ? `<div class="job-group"><div class="section-title">进行中 <span class="muted" style="font-weight:400;font-size:13px">· 合成与改写互不阻塞</span></div>${run.map(card).join("")}</div>` : ""}
    <div class="job-group"><div class="section-title">最近任务</div>${hist.map(card).join("") || '<div class="card empty">暂无历史任务</div>'}</div>`;
  if (manual) toast("已刷新");
}
function goJob(id) {
  const j = JOBS.find(x => x.id === id);
  if (j.chapter) { const idx = Math.max(0, CHAPTERS.findIndex(c => c.title.includes(j.chapter.split("·")[0].trim()))); openChapter(idx >= 0 ? idx : STATE.chIdx); }
  else openBook("agent");
}

/* ---------------- 设置 ---------------- */
let currentEngine = "mimo", playingVoice = null;
function renderSettings() {
  const g = $("#settingsGrid");
  g.innerHTML = `
  <div class="set-group" style="grid-column:1/-1">
    <div class="panel-title" style="margin:0 0 14px">TTS 引擎 <span class="muted" style="font-weight:400;font-size:12px">· 云端 MiMo 与本地 Qwen 可随时切换</span></div>
    <div class="engine-select">
      <button class="engine-tab ${currentEngine==='mimo'?'active':''}" id="eng-mimo" onclick="switchEngine('mimo')">
        <div class="et-name">${currentEngine==='mimo'?'<span class="live-dot"></span>':'<span style="width:8px"></span>'}MiMo · 云端 TTS 2.5</div>
        <div class="et-desc">无需 GPU · 支持并发 5 · 茉莉音色</div>
      </button>
      <button class="engine-tab ${currentEngine==='qwen'?'active':''}" id="eng-qwen" onclick="switchEngine('qwen')">
        <div class="et-name">${currentEngine==='qwen'?'<span class="live-dot"></span>':'<span style="width:8px"></span>'}Qwen · 本机引擎</div>
        <div class="et-desc">RTX 5060 · 建议并发 1–2 · 需加载模型</div>
      </button>
    </div>
    <div class="panel-title" style="font-size:13px;margin-bottom:4px">音色试听 <span class="muted" style="font-weight:400">· 试听文本「你好，世界」</span></div>
    <div class="voice-grid" id="voiceGrid"></div>
  </div>

  <div class="set-group">
    <div class="panel-title">合成参数</div>
    <div class="set-row"><div class="set-label"><b>合成并发</b>云端可调大，本机建议 1–2</div>
      <span class="badge ok" style="font-size:13px"><span id="concVal">5</span></span></div>
    <input type="range" min="1" max="16" value="5" oninput="document.getElementById('concVal').textContent=this.value;toast('已自动保存')" style="width:100%">
    <div class="set-row"><div class="set-label"><b>合成批处理句数</b>一次提交句数</div>
      <div class="seg-select"><button class="icon-btn" style="width:30px;height:30px" onclick="nudge(-1)">−</button><span style="min-width:26px;text-align:center;font-weight:700" id="batchVal">3</span><button class="icon-btn" style="width:30px;height:30px" onclick="nudge(1)">＋</button></div>
    </div>
    <div class="set-row"><div class="set-label"><b>基础语速</b>固化进音频与字幕</div><span class="badge ok">1.25×</span></div>
    <div class="set-row"><div class="set-label"><b>合成模式</b>CustomVoice 选音色</div><select><option>CustomVoice</option><option>Voice Clone</option></select></div>
  </div>

  <div class="set-group">
    <div class="panel-title">改写参数</div>
    <div class="set-row"><div class="set-label"><b>改写并发</b>LLM 通道并发上限</div><span class="badge ok" style="font-size:13px">20</span></div>
    <input type="range" min="1" max="40" value="20" style="width:100%" oninput="toast('已自动保存')">
    <div class="set-row"><div class="set-label"><b>LLM 模型</b>DeepSeek dsv4-flash</div><span class="badge ok">在线</span></div>
    <div class="set-row"><div class="set-label"><b>缩写朗读预处理</b>LLM → L L M</div><span class="badge ok"><span class="bdot"></span>已开启</span></div>
  </div>

  <div class="set-group">
    <div class="panel-title">章节规则</div>
    <div class="set-row"><div class="set-label"><b>章节字数下限</b></div><span style="font-weight:700">5000</span></div>
    <div class="set-row"><div class="set-label"><b>章节字数上限</b></div><span style="font-weight:700">15000</span></div>
    <div class="set-row"><div class="set-label"><b>朗读指示</b>平稳、一致、中性稳定</div><button class="btn btn-ghost btn-sm" onclick="toast('已保存')">编辑</button></div>
  </div>`;
  renderVoices();
}
function switchEngine(eng) {
  currentEngine = eng;
  toast(`已切换到 ${eng === "mimo" ? "MiMo 云端" : "Qwen 本机"}引擎并自动保存`);
  renderSettings();
}
function renderVoices() {
  const voices = currentEngine === "mimo" ? MIMO_VOICES : QWEN_VOICES;
  $("#voiceGrid").innerHTML = voices.map((v, i) => `
    <div class="voice-chip ${v === "茉莉" || v === "vivian" ? "sel" : ""} ${playingVoice === v ? "playing" : ""}" id="voice-${i}">
      <span class="voice-name">${v}</span>
      <button class="play-mini" onclick="event.stopPropagation();previewVoice('${v}')">${playingVoice === v ? '<span class="eq" style="display:flex"><i></i><i></i><i></i></span>' : "▶"}</button>
    </div>`).join("");
}
function previewVoice(name) {
  if (playingVoice === name) { playingVoice = null; toast("已停止试听"); renderVoices(); return; }
  playingVoice = name;
  toast(`正在试听「${name}」· 你好，世界`);
  renderVoices();
  setTimeout(() => { playingVoice = null; renderVoices(); }, 5000);
}
let batchN = 3;
function nudge(d) {
  batchN = Math.min(12, Math.max(1, batchN + d));
  const el = $("#batchVal"); if (el) el.textContent = batchN;
  toast("已自动保存");
}

/* ---------------- 初始化 ---------------- */
document.addEventListener("DOMContentLoaded", () => {
  $$(".nav-item").forEach(n => n.addEventListener("click", () => {
    const v = n.dataset.nav;
    if (v === "book" || v === "chapter") return;
    showView(v);
  }));
  // 拖拽高亮
  const zone = $("#uploadZone");
  ["dragenter", "dragover"].forEach(ev => zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.add("drag"); }));
  ["dragleave", "drop"].forEach(ev => zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.remove("drag"); }));
  zone.addEventListener("drop", () => simulateUpload());
  // 键盘翻章（章节视图）
  document.addEventListener("keydown", e => {
    if (STATE.view !== "chapter") return;
    if (e.key === "ArrowLeft" && STATE.chIdx > 0) openChapter(STATE.chIdx - 1);
    if (e.key === "ArrowRight" && STATE.chIdx < CHAPTERS.length - 1) openChapter(STATE.chIdx + 1);
  });
  // 任务进度模拟
  setInterval(() => {
    if (STATE.view !== "jobs") return;
    const run = JOBS.filter(j => j.status === "run");
    run.forEach(j => { if (j.progress < 100) j.progress = Math.min(100, j.progress + (j.type === "synth" ? 1.5 : 3)); });
    renderJobs();
  }, 1800);
  renderBooks();
  renderJobs();
  renderSettings();
  updateCrumbs();
  // 支持 #books / #book / #chapter / #jobs / #settings 直达（便于截图与分享）
  const hash = (location.hash || "#books").replace("#", "");
  if (hash === "book") openBook("agent");
  else if (hash === "chapter") openChapter(1);
  else if (hash === "jobs") showView("jobs");
  else if (hash === "settings") showView("settings");
  else showView("books");
  toast("欢迎体验 UI 原型 ✦ 点击左侧或卡片切换");
});

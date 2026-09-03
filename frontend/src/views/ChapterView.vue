<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import * as api from "../api/client";
import ChapterEditor from "../components/ChapterEditor.vue";
import { marked } from "marked";
import AudioPlayer from "../components/AudioPlayer.vue";
import { useBooksStore } from "../stores/books";
import { useSettingsStore } from "../stores/settings";
import { useToastStore } from "../stores/toast";
import { waitForJob } from "../utils/jobs";

const route = useRoute();
const router = useRouter();
const books = useBooksStore();
const settingsStore = useSettingsStore();
const toast = useToastStore();
const bookId = ref(route.params.bookId as string);
const chapterId = ref(route.params.chapterId as string);

const md = ref("");
const sourceMd = ref<string | null>(null);
const activeTab = ref<"speech" | "source">("speech");
const saved = ref(false);
const synthesizing = ref(false);
const rewriting = ref(false);
const restoring = ref(false);
const isSource = ref(false);
const rewriteConcurrency = ref(20);
const synthConcurrency = ref(2);
const audioVersion = ref(0);
const error = ref("");

const chapterIndex = computed(() =>
  (books.detail?.chapters ?? []).findIndex((c) => c.id === chapterId.value));
const chapter = computed(() => (books.detail?.chapters ?? [])[chapterIndex.value]);
const chapterTitle = computed(() => chapter.value?.title ?? chapterId.value);
const sourceHtml = computed(() => sourceMd.value ? (marked.parse(sourceMd.value) as string) : "");

const playerRef = ref<InstanceType<typeof AudioPlayer> | null>(null);
const activeMode = ref<"edit" | "follow">("edit");
const segments = ref<api.Segment[]>([]);
const currentTime = ref(0);
const activeSegIdx = computed(() => {
  const t = currentTime.value;
  const i = segments.value.findIndex((seg) => t >= seg.start && t < seg.end);
  return i;
});

function onPlayerTime(t: number) {
  currentTime.value = t;
}
function seekSentence(start: number) {
  playerRef.value?.seekTo(start, true);
}

async function loadChapter() {
  const bId = route.params.bookId as string;
  const cId = route.params.chapterId as string;
  bookId.value = bId;
  chapterId.value = cId;
  audioVersion.value++;
  activeTab.value = "speech";
  activeMode.value = "edit";
  saved.value = false;
  isSource.value = false;
  error.value = "";
  md.value = "";
  sourceMd.value = null;
  segments.value = [];
  currentTime.value = 0;
  try {
    if (books.detail?.book_id !== bId) await books.loadBook(bId);
    md.value = await api.getSpeechMd(bId, cId);
    if (!md.value.trim()) {
      try {
        const src = await api.getSourceMd(bId, cId);
        if (src.trim()) { md.value = src; isSource.value = true; }
      } catch { /* 无原始文本 */ }
    }
    try {
      sourceMd.value = await api.getSourceMd(bId, cId);
    } catch { sourceMd.value = null; }
    try {
      segments.value = await api.getSegments(bId, cId);
    } catch { segments.value = []; }
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? String(e);
  }
}
watch(() => [route.params.bookId, route.params.chapterId] as const, loadChapter, { immediate: true });

// 参数面板默认值跟随设置页（合成并发支持 -1）
async function syncAdvancedDefaults() {
  if (!settingsStore.settings) {
    try { await settingsStore.load(); } catch { /* 忽略：仍用本地默认 */ }
  }
  if (settingsStore.settings) {
    rewriteConcurrency.value = settingsStore.settings.rewrite_concurrency;
    synthConcurrency.value = settingsStore.settings.tts_concurrency;
  }
}
void syncAdvancedDefaults();

async function save() {
  error.value = "";
  try {
    await api.saveSpeechMd(bookId.value, chapterId.value, md.value);
    isSource.value = false;
    toast.show("文本已保存");
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? String(e);
  }
}

async function restore() {
  if (!confirm("确定将本章文本还原为最初的原文（source.md）吗？当前文本会备份到 speech.previous.md。")) return;
  restoring.value = true;
  error.value = "";
  try {
    await api.restoreChapter(bookId.value, chapterId.value);
    md.value = await api.getSpeechMd(bookId.value, chapterId.value);
    isSource.value = true;
    toast.show("已还原为原文");
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? String(e);
  } finally {
    restoring.value = false;
  }
}

async function rewrite() {
  rewriting.value = true;
  error.value = "";
  try {
    const job = await api.rewriteChapter(bookId.value, chapterId.value, rewriteConcurrency.value);
    toast.show("改写任务已开始");
    await waitForJob(job.id);
    md.value = await api.getSpeechMd(bookId.value, chapterId.value);
    isSource.value = false;
    toast.show("改写完成");
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? String(e);
  } finally {
    rewriting.value = false;
  }
}

async function synthesize() {
  synthesizing.value = true;
  error.value = "";
  try {
    const job = await api.synthesizeChapter(bookId.value, chapterId.value, synthConcurrency.value);
    toast.show("合成任务已开始，可在任务中心查看进度");
    await waitForJob(job.id);
    audioVersion.value++;
    if (books.detail?.book_id === bookId.value) await books.loadBook(bookId.value);
    toast.show("本章合成完成");
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? String(e);
  } finally {
    synthesizing.value = false;
  }
}

function goTo(chId: string | null) {
  if (chId && chId !== chapterId.value) router.push(`/books/${bookId.value}/chapters/${chId}`);
}
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1 style="font-size:20px">{{ chapterTitle }}</h1>
        <div class="page-sub">
          <template v-if="books.detail">第 {{ chapterIndex + 1 }} / {{ books.detail.chapters.length }} 章 · </template>
          朗读文本与音频工作台
        </div>
      </div>
      <div class="row">
        <button class="btn btn-ghost btn-sm" :disabled="restoring" @click="restore">还原原文</button>
        <button class="btn btn-soft btn-sm" :disabled="rewriting" @click="rewrite">
          {{ rewriting ? "改写中…" : "改写本章" }}
        </button>
        <button class="btn btn-primary btn-sm" :disabled="synthesizing" @click="synthesize">
          {{ synthesizing ? "合成中…" : "合成本章音频" }}
        </button>
      </div>
    </div>

    <p v-if="isSource" class="hint" style="margin-bottom:14px">当前显示原始抽取文本（本章尚未改写）——可直接编辑保存，或点「改写本章」生成口语化文本。</p>
    <p v-if="error" class="err" style="margin-bottom:12px">{{ error }}</p>

    <div class="wb">
      <div class="panel editor-panel">
        <div class="panel-title">
          <span v-if="activeTab === 'speech'">朗读文本</span>
          <span v-else>原文预览</span>
          <span class="tabs">
            <button class="tab" :class="{ active: activeTab === 'speech' }" @click="activeTab = 'speech'">朗读</button>
            <button class="tab" :class="{ active: activeTab === 'source' }" @click="activeTab = 'source'">原文</button>
          </span>
        </div>
        <div v-if="activeTab === 'speech'" class="subbar">
          <span class="mode-tabs">
            <button class="tab" :class="{ active: activeMode === 'edit' }" @click="activeMode = 'edit'">编辑</button>
            <button class="tab" :class="{ active: activeMode === 'follow' }" @click="activeMode = 'follow'">跟读跳句</button>
          </span>
          <span class="follow-tip" v-if="activeMode === 'follow'">点击句子即可跳转播放</span>
        </div>
        <div v-show="activeTab === 'speech' && activeMode === 'edit'">
          <ChapterEditor v-model="md" />
        </div>
        <div v-show="activeTab === 'speech' && activeMode === 'follow'" class="follow-box">
          <div v-if="segments.length" class="sent-list">
            <button v-for="(seg, i) in segments" :key="seg.index" class="sent"
                    :class="{ on: i === activeSegIdx }" @click="seekSentence(seg.start)">
              <span class="si">{{ seg.index }}</span>
              <span class="st">{{ seg.text }}</span>
            </button>
          </div>
          <div v-else class="docbox empty"><div class="big">🎧</div>本章尚未合成，暂无逐句字幕。先合成，再回来跟读跳句。</div>
          <div class="muted" style="margin-top:8px;font-size:12px">字幕来自合成时生成的独立 segments 文件；若修改过文本，请保存并重新合成以刷新字幕。</div>
        </div>
        <div v-show="activeTab === 'source'">
          <div v-if="sourceMd" class="docbox" v-html="sourceHtml"></div>
          <div v-else class="docbox empty"><div class="big">📄</div>本章尚未解析出原始文本</div>
          <div class="muted" style="margin-top:8px;font-size:12px">原文仅作对照预览，不可编辑；修改请切回「朗读」页签。</div>
        </div>
        <div class="editor-actions">
          <button class="btn btn-ghost btn-sm" @click="save">保存文本</button>
          <span class="kbd">Ctrl+S 思路：保存后重新合成分片才会更新</span>
        </div>
      </div>

      <div class="right-col">
        <div class="panel">
          <div class="panel-title">播放器</div>
          <AudioPlayer ref="playerRef" :key="audioVersion" :book-id="bookId"
                       :chapter-id="chapterId" @time="onPlayerTime" />
        </div>

        <div class="panel">
          <div class="panel-title">参数</div>
          <div class="set-row">
            <span class="set-label"><b>合成并发</b>-1 不限（仅按 RPM 限速）</span>
            <input type="number" v-model.number="synthConcurrency" min="-1" max="64" style="width:70px" />
          </div>
          <div class="set-row">
            <span class="set-label"><b>改写并发</b>LLM 通道上限</span>
            <input type="number" v-model.number="rewriteConcurrency" min="1" max="100" style="width:70px" />
          </div>
        </div>

        <div class="panel">
          <div class="panel-title">翻章</div>
          <div class="row" style="justify-content:space-between">
            <button class="btn btn-ghost btn-sm" :disabled="chapterIndex <= 0"
                    @click="goTo(books.detail?.chapters?.[chapterIndex - 1]?.id ?? null)">← 上一章</button>
            <button class="btn btn-ghost btn-sm" :disabled="chapterIndex < 0 || chapterIndex >= (books.detail?.chapters.length ?? 0) - 1"
                    @click="goTo(books.detail?.chapters?.[chapterIndex + 1]?.id ?? null)">下一章 →</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wb{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:18px;align-items:start}
.editor-panel{min-width:0}
.tabs{display:inline-flex;background:#EDF2F0;border-radius:10px;padding:3px;gap:2px;margin-left:auto}
.tab{padding:5px 12px;border-radius:8px;font-size:12px;color:var(--muted);font-weight:600;transition:.18s}
.tab.active{background:#fff;color:var(--green-700);box-shadow:var(--shadow-sm)}
.subbar{display:flex;align-items:center;gap:12px;margin-bottom:10px}
.mode-tabs{display:inline-flex;background:#EDF2F0;border-radius:10px;padding:3px;gap:2px}
.follow-tip{font-size:12px;color:var(--muted)}
.follow-box{display:flex;flex-direction:column}
.sent-list{height:460px;overflow:auto;border:1px solid var(--line);border-radius:var(--r-md);background:#fff;padding:10px;display:flex;flex-direction:column;gap:4px}
.sent{display:flex;gap:10px;text-align:left;padding:7px 10px;border-radius:9px;line-height:1.75;transition:.18s;border:1px solid transparent}
.sent:hover{background:var(--green-50)}
.sent.on{background:var(--green-100);border-color:var(--green-200)}
.sent.on .si{background:var(--green-600);color:#fff}
.si{flex:none;width:22px;height:22px;border-radius:7px;background:#EDF2F0;color:var(--muted);font-size:11px;display:grid;place-items:center;font-weight:700;margin-top:4px;transition:.18s}
.st{white-space:pre-wrap}
.docbox{border:1px solid var(--line);border-radius:var(--r-md);height:460px;overflow:auto;padding:18px;background:#fff;line-height:1.9;font-size:14px}
.docbox :deep(h1),.docbox :deep(h2),.docbox :deep(h3){margin:12px 0 6px;line-height:1.5}
.docbox :deep(p){margin-bottom:10px}
.docbox :deep(table){border-collapse:collapse;margin:10px 0}
.docbox :deep(td),.docbox :deep(th){border:1px solid var(--line);padding:4px 8px}
.editor-actions{display:flex;align-items:center;gap:10px;margin-top:14px;flex-wrap:wrap}
.right-col{display:flex;flex-direction:column;gap:14px}
.kbd{color:var(--faint);font-size:12px}
.set-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 0;border-bottom:1px dashed var(--line)}
.set-row:last-child{border-bottom:none}
.set-label{font-size:12px;color:var(--muted);line-height:1.4}
.set-label b{color:var(--ink);display:block;font-size:13px}
@media (max-width:900px){.wb{grid-template-columns:1fr}}
</style>

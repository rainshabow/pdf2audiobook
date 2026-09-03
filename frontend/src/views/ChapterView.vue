<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import * as api from "../api/client";
import ChapterEditor from "../components/ChapterEditor.vue";
import AudioPlayer from "../components/AudioPlayer.vue";
import { useBooksStore } from "../stores/books";
import { useToastStore } from "../stores/toast";
import { waitForJob } from "../utils/jobs";

const route = useRoute();
const router = useRouter();
const books = useBooksStore();
const toast = useToastStore();
const bookId = route.params.bookId as string;
const chapterId = route.params.chapterId as string;

const md = ref("");
const saved = ref(false);
const synthesizing = ref(false);
const rewriting = ref(false);
const restoring = ref(false);
const isSource = ref(false);
const rewriteConcurrency = ref(20);
const synthConcurrency = ref(2);
const audioVersion = ref(0);
const error = ref("");

const chapterIndex = computed(() => (books.detail?.chapters ?? []).findIndex((c) => c.id === chapterId));
const chapter = computed(() => (books.detail?.chapters ?? [])[chapterIndex.value]);
const chapterTitle = computed(() => chapter.value?.title ?? chapterId);

onMounted(async () => {
  try {
    if (!books.detail) await books.loadBook(bookId);
    md.value = await api.getSpeechMd(bookId, chapterId);
    if (!md.value.trim()) {
      try {
        const src = await api.getSourceMd(bookId, chapterId);
        if (src.trim()) { md.value = src; isSource.value = true; }
      } catch { /* 无原始文本 */ }
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? String(e);
  }
});

async function save() {
  error.value = "";
  try {
    await api.saveSpeechMd(bookId, chapterId, md.value);
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
    await api.restoreChapter(bookId, chapterId);
    md.value = await api.getSpeechMd(bookId, chapterId);
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
    const job = await api.rewriteChapter(bookId, chapterId, rewriteConcurrency.value);
    toast.show("改写任务已开始");
    await waitForJob(job.id);
    md.value = await api.getSpeechMd(bookId, chapterId);
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
    const job = await api.synthesizeChapter(bookId, chapterId, synthConcurrency.value);
    toast.show("合成任务已开始，可在任务中心查看进度");
    await waitForJob(job.id);
    audioVersion.value++;
    if (books.detail) await books.loadBook(bookId);
    toast.show("本章合成完成");
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? String(e);
  } finally {
    synthesizing.value = false;
  }
}

function goTo(chId: string | null) {
  if (chId) router.push(`/books/${bookId}/chapters/${chId}`);
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
        <div class="panel-title">朗读文本
          <span class="ok" style="font-size:12px;font-weight:400" v-if="saved">✓ 已保存</span>
        </div>
        <ChapterEditor v-model="md" />
        <div class="editor-actions">
          <button class="btn btn-ghost btn-sm" @click="save">保存文本</button>
          <span class="kbd">Ctrl+S 思路：保存后重新合成分片才会更新</span>
        </div>
      </div>

      <div class="right-col">
        <div class="panel">
          <div class="panel-title">播放器</div>
          <AudioPlayer :key="audioVersion" :book-id="bookId" :chapter-id="chapterId" />
        </div>

        <div class="panel">
          <div class="panel-title">参数</div>
          <div class="set-row">
            <span class="set-label"><b>合成并发</b>本机 1–2 / 云端可大</span>
            <input type="number" v-model.number="synthConcurrency" min="1" max="32" style="width:70px" />
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
.editor-actions{display:flex;align-items:center;gap:10px;margin-top:14px;flex-wrap:wrap}
.right-col{display:flex;flex-direction:column;gap:14px}
.kbd{color:var(--faint);font-size:12px}
.set-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 0;border-bottom:1px dashed var(--line)}
.set-row:last-child{border-bottom:none}
.set-label{font-size:12px;color:var(--muted);line-height:1.4}
.set-label b{color:var(--ink);display:block;font-size:13px}
@media (max-width:900px){.wb{grid-template-columns:1fr}}
</style>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { ChapterInfo } from "../api/client";
import { useBooksStore } from "../stores/books";
import { useToastStore } from "../stores/toast";
import { waitForJob } from "../utils/jobs";
import ChapterTree from "../components/ChapterTree.vue";

const route = useRoute();
const router = useRouter();
const books = useBooksStore();
const toast = useToastStore();
const busy = ref(false);
const error = ref("");
const rewriteConcurrency = ref(20);
const synthConcurrency = ref(2);
const bookId = route.params.bookId as string;

onMounted(async () => {
  await books.loadBook(bookId);
  if (books.detail) books.refreshBooks();
});

const hasParsed = computed(() => (books.detail?.chapters.length ?? 0) > 0);
const hasRewritten = computed(() =>
  (books.detail?.chapters ?? []).some((c) => c.status !== "pending"));
const synthCount = computed(() =>
  (books.detail?.chapters ?? []).filter((c) => c.audio_duration > 0).length);
const totalChapters = computed(() => books.detail?.chapters.length ?? 0);
const allSynthesized = computed(() =>
  totalChapters.value > 0 && synthCount.value === totalChapters.value);

const steps = computed(() => [
  { txt: "解析章节", state: hasParsed.value ? "done" : "now" },
  { txt: "口语化改写", state: hasParsed.value && !hasRewritten.value ? "now" : (hasRewritten.value ? "done" : "wait") },
  { txt: "分章合成", state: allSynthesized.value ? "done" : (hasRewritten.value ? "now" : "wait") },
]);

async function run(type: "parse" | "rewrite" | "synthesize") {
  busy.value = true;
  error.value = "";
  try {
    await startAndPoll(type);
    await books.loadBook(bookId);
    toast.show(type === "parse" ? "解析完成" : type === "rewrite" ? "改写完成" : "合成完成");
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? String(e);
  } finally {
    busy.value = false;
  }
}

async function startAndPoll(type: "parse" | "rewrite" | "synthesize") {
  const api = await import("../api/client");
  const conc = type === "rewrite" ? rewriteConcurrency.value
    : type === "synthesize" ? synthConcurrency.value : undefined;
  const job = await api.startJob(bookId, type, conc);
  toast.show(type === "parse" ? "解析任务已开始" : type === "rewrite" ? "改写任务已开始" : "合成任务已开始");
  await waitForJob(job.id);
}

async function synthesizeChapter(ch: ChapterInfo) {
  const api = await import("../api/client");
  busy.value = true;
  error.value = "";
  try {
    const job = await api.synthesizeChapter(bookId, ch.id, synthConcurrency.value);
    toast.show(`合成已开始：${ch.title}`);
    await waitForJob(job.id);
    await books.loadBook(bookId);
    toast.show("本章合成完成");
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? String(e);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div v-if="books.detail">
    <div class="page-head">
      <div>
        <h1>{{ books.detail.title }}</h1>
        <div class="page-sub">{{ books.detail.page_count }} 页 · {{ books.detail.chapters.length }} 章 · 全流程在此完成</div>
      </div>
      <div class="row">
        <button class="btn btn-ghost" :disabled="busy" @click="router.push('/')">返回书架</button>
        <button v-if="!hasParsed" class="btn btn-primary" :disabled="busy" @click="run('parse')">
          {{ busy ? "处理中…" : "① 解析章节" }}
        </button>
        <button v-else-if="!hasRewritten" class="btn btn-primary" :disabled="busy" @click="run('rewrite')">
          {{ busy ? "处理中…" : "② 口语化改写" }}
        </button>
        <button v-else-if="!allSynthesized" class="btn btn-primary" :disabled="busy" @click="run('synthesize')">
          {{ busy ? "处理中…" : "③ 全部合成" }}
        </button>
        <button v-else class="btn btn-soft" disabled>全部完成 ✓</button>
      </div>
    </div>

    <div class="stepper">
      <template v-for="(s, i) in steps" :key="s.txt">
        <div class="step" :class="s.state">
          <span class="step-num">{{ s.state === "done" ? "✓" : i + 1 }}</span>
          <span class="step-txt">{{ s.txt }}</span>
        </div>
        <div v-if="i < steps.length - 1" class="step-line"><span class="fill"></span></div>
      </template>
    </div>

    <div class="adv-row" v-if="hasRewritten || hasParsed">
      <label class="adv">改写并发
        <input type="number" v-model.number="rewriteConcurrency" min="1" max="100" />
      </label>
      <label class="adv">合成并发
        <input type="number" v-model.number="synthConcurrency" min="1" max="32" />
      </label>
      <span class="muted tip">改写与合成走双通道，可同时运行</span>
    </div>
    <p v-if="error" class="err">{{ error }}</p>

    <div class="section-title" style="margin-top:22px">
      章节 <span class="muted" style="font-weight:400;font-size:13px">· 点击整行进入章节工作台</span>
    </div>
    <ChapterTree :detail="books.detail" @open="(ch) => router.push(`/books/${bookId}/chapters/${ch.id}`)" @synthesize="synthesizeChapter" />
  </div>
</template>

<style scoped>
.stepper{display:flex;align-items:center;background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);padding:13px 18px;box-shadow:var(--shadow-sm);margin-bottom:12px;flex-wrap:wrap;gap:6px}
.step{display:flex;align-items:center;gap:9px}
.step-num{width:29px;height:29px;border-radius:50%;display:grid;place-items:center;font-weight:700;font-size:12.5px;background:#EDF2F0;color:var(--muted);transition:.25s var(--ease);flex:none}
.step.done .step-num{background:var(--green-500);color:#fff}
.step.now .step-num{background:var(--green-600);color:#fff;animation:pulse-ring 2s infinite}
.step-txt{font-size:13px;color:var(--muted);white-space:nowrap}
.step.now .step-txt{color:var(--ink);font-weight:700}
.step-line{width:38px;height:2px;background:var(--line);border-radius:2px;overflow:hidden}
.step-line .fill{display:block;height:100%;width:0;background:var(--green-500);transition:width .4s var(--ease)}
.step.done .step-line .fill{width:100%}
.adv-row{display:flex;gap:16px;align-items:center;margin:2px 2px 14px;flex-wrap:wrap}
.adv{font-size:12px;color:var(--muted);display:flex;align-items:center;gap:6px}
.adv input{width:62px;padding:4px 8px}
.tip{font-size:12px}
</style>

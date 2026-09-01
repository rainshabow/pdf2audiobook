<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { ChapterInfo } from "../api/client";
import { useBooksStore } from "../stores/books";
import { waitForJob } from "../utils/jobs";
import ChapterTree from "../components/ChapterTree.vue";

const route = useRoute();
const router = useRouter();
const books = useBooksStore();
const busy = ref(false);
const error = ref("");

onMounted(async () => {
  await books.loadBook(route.params.bookId as string);
  if (books.detail) books.refreshBooks();
});

async function run(type: "parse" | "rewrite" | "synthesize") {
  busy.value = true;
  error.value = "";
  try {
    await startAndPoll(type);
    await books.loadBook(route.params.bookId as string);
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? String(e);
  } finally {
    busy.value = false;
  }
}

async function startAndPoll(type: "parse" | "rewrite" | "synthesize") {
  const api = await import("../api/client");
  const job = await api.startJob(route.params.bookId as string, type);
  await waitForJob(job.id);
}

function open(ch: ChapterInfo) {
  router.push(`/books/${route.params.bookId}/chapters/${ch.id}`);
}
</script>

<template>
  <div v-if="books.detail">
    <h2>{{ books.detail.title }}</h2>
    <p>共 {{ books.detail.page_count }} 页，{{ books.detail.chapters.length }} 章</p>
    <div class="actions">
      <button :disabled="busy" @click="run('parse')">① 解析章节</button>
      <button :disabled="busy" @click="run('rewrite')">② 全部改写</button>
      <button :disabled="busy" @click="run('synthesize')">③ 合成语音</button>
      <span v-if="error" class="err">{{ error }}</span>
    </div>
    <ChapterTree :detail="books.detail" @open="open" />
  </div>
</template>

<style scoped>
.actions { display: flex; gap: 12px; margin-bottom: 16px; }
.err { color: #c00; }
</style>
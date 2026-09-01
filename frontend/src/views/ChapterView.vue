<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import * as api from "../api/client";
import ChapterEditor from "../components/ChapterEditor.vue";
import AudioPlayer from "../components/AudioPlayer.vue";

const route = useRoute();
const bookId = route.params.bookId as string;
const chapterId = route.params.chapterId as string;
const md = ref("");
const saved = ref(false);
const rebuilding = ref(false);
const error = ref("");

onMounted(async () => {
  md.value = await api.getSpeechMd(bookId, chapterId);
});

async function save() {
  await api.saveSpeechMd(bookId, chapterId, md.value);
  saved.value = true;
  setTimeout(() => (saved.value = false), 2000);
}
async function rebuild() {
  rebuilding.value = true;
  error.value = "";
  try {
    const job = await api.rebuildChapter(bookId, chapterId);
    while (true) {
      await new Promise((r) => setTimeout(r, 1500));
      const jobs = await api.listJobs();
      const cur = jobs.find((j) => j.id === job.id);
      if (!cur || cur.status === "done") break;
      if (cur.status === "failed" || cur.status === "cancelled") throw new Error(cur.error ?? cur.status);
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? String(e);
  } finally {
    rebuilding.value = false;
  }
}
</script>

<template>
  <div>
    <h3>{{ chapterId }}</h3>
    <ChapterEditor v-model="md" />
    <div class="bar">
      <button @click="save">保存文本</button>
      <button :disabled="rebuilding" @click="rebuild">重建本章音频</button>
      <span v-if="saved" class="ok">已保存</span>
      <span v-if="error" class="err">{{ error }}</span>
    </div>
    <AudioPlayer :book-id="bookId" :chapter-id="chapterId" />
  </div>
</template>

<style scoped>
.bar { display: flex; gap: 12px; align-items: center; margin: 12px 0; }
.ok { color: #080; }
.err { color: #c00; }
</style>
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import * as api from "../api/client";
import ChapterEditor from "../components/ChapterEditor.vue";
import AudioPlayer from "../components/AudioPlayer.vue";
import { waitForJob } from "../utils/jobs";

const route = useRoute();
const bookId = route.params.bookId as string;
const chapterId = route.params.chapterId as string;
const md = ref("");
const saved = ref(false);
const rebuilding = ref(false);
const error = ref("");
const audioVersion = ref(0);

onMounted(async () => {
  try {
    md.value = await api.getSpeechMd(bookId, chapterId);
  } catch (e: any) {
    md.value = "";
    error.value = e?.response?.data?.detail ?? String(e);
  }
});

async function save() {
  error.value = "";
  try {
    await api.saveSpeechMd(bookId, chapterId, md.value);
    saved.value = true;
    setTimeout(() => (saved.value = false), 2000);
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? String(e);
  }
}
async function rebuild() {
  rebuilding.value = true;
  error.value = "";
  try {
    const job = await api.rebuildChapter(bookId, chapterId);
    await waitForJob(job.id);
    audioVersion.value++;
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
    <AudioPlayer :key="audioVersion" :book-id="bookId" :chapter-id="chapterId" />
  </div>
</template>

<style scoped>
.bar { display: flex; gap: 12px; align-items: center; margin: 12px 0; }
.ok { color: #080; }
.err { color: #c00; }
</style>
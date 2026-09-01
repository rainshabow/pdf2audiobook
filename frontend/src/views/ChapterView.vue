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
const synthesizing = ref(false);
const rewriting = ref(false);
const isSource = ref(false);
const error = ref("");
const audioVersion = ref(0);

onMounted(async () => {
  try {
    md.value = await api.getSpeechMd(bookId, chapterId);
    if (!md.value.trim()) {
      // 尚未改写：回退展示原始抽取文本，避免预览为空
      try {
        const src = await api.getSourceMd(bookId, chapterId);
        if (src.trim()) {
          md.value = src;
          isSource.value = true;
        }
      } catch { /* 无原始文本 */ }
    }
  } catch (e: any) {
    md.value = "";
    error.value = e?.response?.data?.detail ?? String(e);
  }
});

async function save() {
  error.value = "";
  try {
    await api.saveSpeechMd(bookId, chapterId, md.value);
    isSource.value = false;  // 保存后即为 speech.md
    saved.value = true;
    setTimeout(() => (saved.value = false), 2000);
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? String(e);
  }
}
async function rewrite() {
  rewriting.value = true;
  error.value = "";
  try {
    const job = await api.rewriteChapter(bookId, chapterId);
    await waitForJob(job.id);
    md.value = await api.getSpeechMd(bookId, chapterId);
    isSource.value = false;
    saved.value = true;
    setTimeout(() => (saved.value = false), 2000);
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
    const job = await api.synthesizeChapter(bookId, chapterId);
    await waitForJob(job.id);
    audioVersion.value++;
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? String(e);
  } finally {
    synthesizing.value = false;
  }
}
</script>

<template>
  <div>
    <h3>{{ chapterId }}</h3>
    <ChapterEditor v-model="md" />
    <p v-if="isSource" class="hint">当前为原始抽取文本（本章尚未改写）——可直接编辑保存，或点「改写本章」生成口语化文本。</p>
    <div class="bar">
      <button @click="save">保存文本</button>
      <button :disabled="rewriting" @click="rewrite">改写本章</button>
      <button :disabled="synthesizing" @click="synthesize">合成本章音频</button>
      <span v-if="saved" class="ok">已保存</span>
      <span v-if="error" class="err">{{ error }}</span>
    </div>
    <AudioPlayer :key="audioVersion" :book-id="bookId" :chapter-id="chapterId" />
  </div>
</template>

<style scoped>
.bar { display: flex; gap: 12px; align-items: center; margin: 12px 0; }
.hint { color: #b26a00; background: #fff4e0; padding: 6px 10px; border-radius: 6px; }
.ok { color: #080; }
.err { color: #c00; }
</style>
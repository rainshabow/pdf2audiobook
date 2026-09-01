<script setup lang="ts">
import type { BookDetail, ChapterInfo } from "../api/client";

defineProps<{ detail: BookDetail }>();
const emit = defineEmits<{
  (e: "open", ch: ChapterInfo): void;
  (e: "synthesize", ch: ChapterInfo): void;
}>();

const statusText: Record<string, string> = {
  pending: "待改写", rewritten: "待合成", synthesized: "已完成", partial: "部分合成", edited: "已编辑", failed: "失败",
};
</script>

<template>
  <ul class="tree">
    <li v-for="ch in detail.chapters" :key="ch.id">
      <span class="title">{{ ch.title }}</span>
      <span class="pages">p{{ ch.page_start }}–{{ ch.page_end }} · {{ ch.char_count }} 字</span>
      <span class="status" :data-status="ch.status">{{ statusText[ch.status] ?? ch.status }}</span>
      <span v-if="ch.audio_duration" class="dur">{{ Math.round(ch.audio_duration) }}s</span>
      <button @click="emit('open', ch)">编辑/播放</button>
      <button @click="emit('synthesize', ch)">合成</button>
    </li>
  </ul>
</template>

<style scoped>
.tree { list-style: none; padding: 0; }
.tree li { display: flex; gap: 12px; align-items: center; padding: 8px; background: #fff; margin-bottom: 6px; border-radius: 6px; }
.title { flex: 1; font-weight: 600; }
.pages { color: #888; font-size: 12px; }
.status { font-size: 12px; padding: 2px 8px; border-radius: 10px; background: #eee; }
.status[data-status="synthesized"] { background: #cfe8cf; }
.status[data-status="failed"] { background: #f3c6c6; }
.dur { color: #666; font-size: 12px; }
</style>
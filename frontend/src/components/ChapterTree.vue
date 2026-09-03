<script setup lang="ts">
import type { BookDetail, ChapterInfo } from "../api/client";

defineProps<{ detail: BookDetail }>();
const emit = defineEmits<{
  (e: "open", ch: ChapterInfo): void;
  (e: "synthesize", ch: ChapterInfo): void;
}>();

const statusText: Record<string, [string, string]> = {
  pending: ["待改写", "wait"],
  rewritten: ["待合成", "ok"],
  synthesized: ["已完成", "ok"],
  partial: ["部分合成", "run"],
  edited: ["已编辑", "wait"],
  failed: ["失败", "err"],
};
</script>

<template>
  <div class="ch-list">
    <div v-for="(ch, i) in detail.chapters" :key="ch.id" class="ch-row"
         :style="{ animationDelay: `${i * 40}ms` }" @click="emit('open', ch)">
      <span class="ch-num">{{ String(i + 1).padStart(2, "0") }}</span>
      <div class="ch-main">
        <div class="ch-title">{{ ch.title }}</div>
        <div class="ch-meta">p{{ ch.page_start }}–{{ ch.page_end }} · {{ ch.char_count.toLocaleString() }} 字</div>
      </div>
      <span v-if="ch.audio_duration" class="ch-dur">{{ Math.round(ch.audio_duration / 60) }} 分</span>
      <span class="badge" :class="statusText[ch.status]?.[1] ?? 'wait'">
        <span class="bdot"></span>{{ statusText[ch.status]?.[0] ?? ch.status }}
      </span>
      <div class="ch-actions" @click.stop>
        <button v-if="ch.status === 'synthesized'" class="btn btn-soft btn-sm" @click="emit('open', ch)">▶ 播放</button>
        <button v-else class="btn btn-primary btn-sm" @click="emit('synthesize', ch)">合成</button>
        <button class="btn btn-ghost btn-sm" @click="emit('open', ch)">编辑</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ch-list{display:flex;flex-direction:column;gap:10px}
.ch-row{display:flex;align-items:center;gap:14px;background:var(--surface);border:1px solid var(--line);border-radius:var(--r-md);padding:12px 16px;cursor:pointer;box-shadow:var(--shadow-sm);transition:transform .18s var(--ease),box-shadow .18s,border-color .18s;animation:fadeUp .35s var(--ease) both}
.ch-row:hover{transform:translateX(4px);border-color:var(--green-200);box-shadow:var(--shadow-md)}
@keyframes fadeUp{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.ch-num{width:38px;height:38px;border-radius:11px;background:#EDF2F0;color:var(--muted);display:grid;place-items:center;font-weight:700;font-size:13px;flex:none}
.ch-main{flex:1;min-width:0}
.ch-title{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ch-meta{color:var(--muted);font-size:12px;margin-top:2px}
.ch-dur{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.ch-actions{display:flex;gap:6px;opacity:0;transform:translateX(6px);transition:.18s var(--ease)}
.ch-row:hover .ch-actions{opacity:1;transform:none}
@media (max-width:720px){.ch-actions{opacity:1;transform:none}.ch-dur{display:none}}
</style>

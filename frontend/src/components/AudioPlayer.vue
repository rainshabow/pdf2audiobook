<script setup lang="ts">
import { ref } from "vue";
import { audioUrl, vttUrl } from "../api/client";

const props = defineProps<{ bookId: string; chapterId: string }>();
const rate = ref(1);
const cueText = ref("");
const audioEl = ref<HTMLAudioElement | null>(null);

function onRate(e: Event) {
  rate.value = Number((e.target as HTMLSelectElement).value);
  if (audioEl.value) audioEl.value.playbackRate = rate.value;
}
function onTime() {
  const el = audioEl.value;
  if (!el || !el.textTracks?.length) return;
  const track = el.textTracks[0];
  for (const c of track.activeCues ?? []) {
    cueText.value = (c as VTTCue).text;
    return;
  }
  cueText.value = "";
}
</script>

<template>
  <div class="player">
    <audio ref="audioEl" :src="audioUrl(bookId, chapterId)" controls
           @timeupdate="onTime">
      <track kind="subtitles" :src="vttUrl(bookId, chapterId)" default />
    </audio>
    <label class="rate-row">倍速
      <select :value="rate" @change="onRate">
        <option v-for="r in [0.5, 0.75, 1, 1.25, 1.5, 2]" :key="r" :value="r">{{ r }}×</option>
      </select>
    </label>
    <p v-if="cueText" class="cue">{{ cueText }}</p>
  </div>
</template>

<style scoped>
.player{display:flex;flex-direction:column;gap:10px}
.player audio{width:100%;height:44px;border-radius:12px}
.rate-row{display:flex;align-items:center;gap:10px;font-size:13px;color:var(--muted)}
.cue{background:#0F241C;color:#D9F5E9;padding:12px 14px;border-radius:var(--r-md);min-height:56px;font-size:13.5px;line-height:1.7;transition:.2s}
</style>
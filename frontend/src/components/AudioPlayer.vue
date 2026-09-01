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
    <label>倍速
      <select :value="rate" @change="onRate">
        <option v-for="r in [0.5, 0.75, 1, 1.25, 1.5, 2]" :key="r" :value="r">{{ r }}×</option>
      </select>
    </label>
    <p v-if="cueText" class="cue">{{ cueText }}</p>
  </div>
</template>

<style scoped>
.player { display: flex; flex-direction: column; gap: 8px; }
.cue { background: #222; color: #fff; padding: 8px; border-radius: 6px; min-height: 1.2em; }
</style>
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { audioUrl, vttUrl } from "../api/client";

const props = defineProps<{ bookId: string; chapterId: string; version?: number }>();
const emit = defineEmits<{ (e: "time", t: number): void }>();

const src = computed(() =>
  audioUrl(props.bookId, props.chapterId, props.version ?? 0));
const vtt = computed(() =>
  vttUrl(props.bookId, props.chapterId, props.version ?? 0));

const audioEl = ref<HTMLAudioElement | null>(null);
const playing = ref(false);
const currentTime = ref(0);
const duration = ref(0);
const rate = ref(1);
const cueText = ref("");
const cues = ref<Array<{ start: number; end: number; text: string }>>([]);

function fmt(t: number) {
  if (!Number.isFinite(t)) return "00:00";
  const s = Math.max(0, Math.floor(t));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

function parseVtt(raw: string) {
  const list: Array<{ start: number; end: number; text: string }> = [];
  const lines = raw.replace(/\r/g, "").split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();
    if (line.includes("-->")) {
      const [a, b] = line.split("-->");
      const toSec = (s: string) => {
        const p = s.trim().split(":");
        const last = p.pop() ?? "0";
        const [sec, ms = "0"] = last.split(".");
        let t = Number(sec) + Number(ms) / 1000;
        if (p.length) t += Number(p.pop()) * 60;
        if (p.length) t += Number(p.pop()) * 3600;
        return t;
      };
      const texts: string[] = [];
      i++;
      while (i < lines.length && lines[i].trim() !== "") { texts.push(lines[i]); i++; }
      list.push({ start: toSec(a), end: toSec(b), text: texts.join("\n").trim() });
    } else i++;
  }
  cues.value = list;
}

async function loadCues() {
  cueText.value = "";
  try {
    const res = await fetch(vtt.value);
    if (res.ok) parseVtt(await res.text());
  } catch { cues.value = []; }
}

function syncCue(t: number) {
  const hit = cues.value.find((c) => t >= c.start && t < c.end);
  cueText.value = hit?.text ?? "";
}

function onTime() {
  const el = audioEl.value;
  if (!el) return;
  currentTime.value = el.currentTime;
  syncCue(el.currentTime);
  emit("time", el.currentTime);
}
function onMeta() {
  const el = audioEl.value;
  if (!el) return;
  duration.value = el.duration || 0;
}
function seek(e: Event) {
  const el = audioEl.value;
  if (!el) return;
  const v = Number((e.target as HTMLInputElement).value);
  seekTo(v);
}
function seekTo(t: number, autoplay = false) {
  const el = audioEl.value;
  if (!el) return;
  el.currentTime = t;
  currentTime.value = t;
  syncCue(t);
  if (autoplay) void el.play();
}
function toggle() {
  const el = audioEl.value;
  if (!el) return;
  if (el.paused) void el.play(); else el.pause();
}
function onRate(e: Event) {
  rate.value = Number((e.target as HTMLSelectElement).value);
  if (audioEl.value) audioEl.value.playbackRate = rate.value;
}
defineExpose({ seekTo });

watch(src, () => {
  currentTime.value = 0;
  duration.value = 0;
  playing.value = false;
  cueText.value = "";
  void loadCues();
}, { immediate: true });
</script>

<template>
  <div class="player">
    <audio ref="audioEl" :src="src" preload="metadata" hidden
           @timeupdate="onTime" @loadedmetadata="onMeta" @durationchange="onMeta"
           @play="playing = true" @pause="playing = false" @ended="playing = false" />

    <div class="p-row">
      <button class="pp" :class="{ on: playing }" @click="toggle" :aria-label="playing ? '暂停' : '播放'">
        <svg v-if="!playing" width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
        <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>
      </button>
      <div class="bar-wrap">
        <input class="seek" type="range" min="0" :max="duration || 0" step="0.1"
               :value="currentTime" @input="seek" :disabled="!duration" />
        <div class="times"><span>{{ fmt(currentTime) }}</span><span>{{ fmt(duration) }}</span></div>
      </div>
      <select class="rate" :value="rate" @change="onRate">
        <option v-for="r in [0.5, 0.75, 1, 1.25, 1.5, 2]" :key="r" :value="r">{{ r }}×</option>
      </select>
    </div>

    <div class="cue" :class="{ idle: !cueText }">
      <span v-if="cueText">{{ cueText }}</span>
      <span v-else class="cue-idle">▶ 播放后这里会同步显示当前句字幕</span>
    </div>
  </div>
</template>

<style scoped>
.player{display:flex;flex-direction:column;gap:12px}
.p-row{display:flex;align-items:center;gap:12px}
.pp{width:46px;height:46px;border-radius:50%;background:linear-gradient(135deg,var(--green-500),var(--green-700));color:#fff;display:grid;place-items:center;box-shadow:0 6px 16px rgba(5,150,105,.3);transition:transform .15s var(--ease),box-shadow .2s;flex:none}
.pp:hover{transform:scale(1.06);box-shadow:0 9px 22px rgba(5,150,105,.4)}
.pp:active{transform:scale(.95)}
.pp.on{animation:pulse-ring 2s infinite}
.bar-wrap{flex:1;min-width:0}
.seek{width:100%;accent-color:var(--green-600);cursor:pointer}
.times{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums;margin-top:2px}
.rate{border:1px solid var(--line);border-radius:9px;padding:6px 8px;background:#fff;color:var(--ink);flex:none}
.cue{background:#0F241C;color:#D9F5E9;padding:12px 14px;border-radius:var(--r-md);min-height:60px;font-size:13.5px;line-height:1.8;border:1px solid rgba(16,185,129,.25);transition:.2s}
.cue-idle{color:#5D7F73;font-size:12.5px}
</style>

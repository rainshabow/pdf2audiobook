<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useJobsStore } from "../stores/jobs";
import { useSettingsStore } from "../stores/settings";

const jobs = useJobsStore();
const settings = useSettingsStore();
const engineLabel = ref("引擎");
const engineName = computed(() => {
  const e = settings.settings?.tts_engine;
  if (e === "mimo") return "MiMo · 云端";
  if (e === "qwen_webui") return "Qwen · 本机";
  if (e === "mock") return "Mock · 测试";
  return "引擎";
});
onMounted(async () => {
  try { await settings.load(); } catch { /* 引擎信息不可用时不展示 */ }
});
</script>

<template>
  <aside class="sidebar">
    <router-link to="/" class="brand">
      <span class="brand-mark">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
      </span>
      <span>
        <span class="brand-name">听书工坊</span>
        <span class="brand-sub">PDF → 有声书</span>
      </span>
    </router-link>

    <div class="nav-label">工作台</div>
    <router-link to="/" class="nav-item" exact-active-class="active">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
      书架
    </router-link>
    <router-link to="/jobs" class="nav-item" active-class="active">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
      任务中心
      <span v-if="jobs.active" class="nav-dot" title="有任务进行中"></span>
    </router-link>

    <div class="nav-label">系统</div>
    <router-link to="/settings" class="nav-item" active-class="active">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
      设置
    </router-link>

    <div class="side-foot">
      <div class="engine-pill">
        <span class="live-dot"></span>
        <span>{{ engineName }}</span>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar{background:var(--surface);border-right:1px solid var(--line);display:flex;flex-direction:column;padding:18px 14px;gap:6px;overflow-y:auto}
.brand{display:flex;align-items:center;gap:10px;padding:4px 8px 18px}
.brand-mark{width:38px;height:38px;border-radius:12px;background:linear-gradient(135deg,var(--green-500),var(--green-700));display:grid;place-items:center;color:#fff;box-shadow:var(--shadow-md);flex:none}
.brand-name{font-weight:700;font-size:15px;display:block}
.brand-sub{font-size:11px;color:var(--muted);margin-top:2px;display:block}
.nav-label{font-size:11px;color:var(--faint);padding:14px 10px 6px;letter-spacing:1px}
.nav-item{display:flex;align-items:center;gap:11px;width:100%;padding:10px 12px;border-radius:var(--r-md);color:var(--muted);font-weight:500;transition:background .18s var(--ease),color .18s var(--ease);position:relative;margin-bottom:2px}
.nav-item svg{flex:none}
.nav-item:hover{background:var(--green-50);color:var(--green-700)}
.nav-item.active{background:var(--green-50);color:var(--green-700);font-weight:600}
.nav-item.active::before{content:"";position:absolute;left:-14px;top:18%;bottom:18%;width:4px;border-radius:0 4px 4px 0;background:var(--green-500)}
.nav-dot{width:8px;height:8px;border-radius:50%;background:var(--amber);margin-left:auto;box-shadow:0 0 0 3px var(--amber-bg)}
.side-foot{margin-top:auto;border-top:1px solid var(--line);padding:14px 10px 4px}
.engine-pill{display:flex;align-items:center;gap:9px;background:var(--green-50);border:1px solid var(--green-100);border-radius:var(--r-md);padding:9px 11px;font-size:12px;color:var(--green-700);font-weight:600}
</style>

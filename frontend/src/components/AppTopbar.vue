<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

const route = useRoute();
const router = useRouter();

const crumbs = computed(() => {
  const p = route.path;
  if (p.startsWith("/books/") && p.includes("/chapters/")) {
    const m = p.match(/\/books\/([^/]+)\/chapters\/([^/]+)/);
    return [
      { label: "书架", to: "/" },
      { label: "书籍工作台", to: `/books/${m?.[1]}` },
      { label: "章节工作台", current: true },
    ];
  }
  if (p.startsWith("/books/")) {
    const m = p.match(/\/books\/([^/]+)/);
    return [
      { label: "书架", to: "/" },
      { label: "书籍工作台", to: m ? `/books/${m[1]}` : "/", current: true },
    ];
  }
  const map: Record<string, [string, string?]> = {
    "/": ["书架"],
    "/jobs": ["任务中心"],
    "/settings": ["设置"],
  };
  const hit = map[p] ?? map["/"];
  return [{ label: hit[0], current: true }];
});
</script>

<template>
  <header class="topbar">
    <div class="crumbs">
      <template v-for="(c, i) in crumbs" :key="i">
        <span v-if="i" class="crumb-sep">›</span>
        <router-link v-if="c.to" :to="c.to" class="crumb link">{{ c.label }}</router-link>
        <span v-else class="crumb current">{{ c.label }}</span>
      </template>
    </div>
    <div class="spacer"></div>
    <button class="icon-btn" title="任务中心" @click="router.push('/jobs')">
      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
    </button>
    <span class="avatar" @click="router.push('/settings')">R</span>
  </header>
</template>

<style scoped>
.topbar{display:flex;align-items:center;gap:12px;padding:13px 28px;background:rgba(255,255,255,.72);backdrop-filter:blur(10px);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:30}
.spacer{flex:1}
.avatar{width:38px;height:38px;border-radius:50%;background:var(--green-100);color:var(--green-700);font-weight:700;display:grid;place-items:center;cursor:pointer;transition:transform .15s var(--ease)}
.avatar:hover{transform:scale(1.06)}
</style>

<script setup lang="ts">
import { onMounted } from "vue";
import { useJobsStore } from "./stores/jobs";

const jobs = useJobsStore();
onMounted(() => jobs.startPolling());
</script>

<template>
  <div class="app">
    <header>
      <router-link to="/">📚 书架</router-link>
      <router-link to="/jobs">⚙️ 任务中心</router-link>
      <router-link to="/settings">🛠 设置</router-link>
      <span v-if="jobs.active" class="dot">●</span>
    </header>
    <main>
      <router-view v-slot="{ Component }">
        <KeepAlive include="SettingsView">
          <component :is="Component" />
        </KeepAlive>
      </router-view>
    </main>
  </div>
</template>

<style>
body { margin: 0; font-family: system-ui, sans-serif; background: #f5f6fa; }
.app { max-width: 1100px; margin: 0 auto; padding: 16px; }
header { display: flex; gap: 16px; align-items: center; padding: 12px 0; border-bottom: 1px solid #ddd; margin-bottom: 16px; }
header a { text-decoration: none; color: #333; font-weight: 600; }
.dot { color: #e11; font-size: 12px; }
</style>

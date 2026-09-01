<script setup lang="ts">
import { useJobsStore } from "../stores/jobs";

const jobs = useJobsStore();

const typeText: Record<string, string> = {
  parse: "解析", rewrite: "改写", synthesize: "合成", rebuild: "重建",
};
const statusText: Record<string, string> = {
  pending: "排队中", running: "进行中", done: "完成", failed: "失败", cancelled: "已取消",
};
</script>

<template>
  <div>
    <table>
      <thead><tr><th>任务</th><th>书籍</th><th>状态</th><th>进度</th><th>错误</th><th></th></tr></thead>
      <tbody>
        <tr v-for="j in jobs.jobs" :key="j.id">
          <td>{{ typeText[j.type] ?? j.type }}</td>
          <td>{{ j.book_id.slice(0, 8) }}<span v-if="j.chapter_id"> / {{ j.chapter_id }}</span></td>
          <td>{{ statusText[j.status] ?? j.status }}</td>
          <td>
            <progress :value="j.progress" max="1"></progress>
            {{ Math.round(j.progress * 100) }}%
          </td>
          <td class="err">{{ j.error }}</td>
          <td><button v-if="['pending', 'running'].includes(j.status)" @click="jobs.cancel(j.id)">取消</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
table { width: 100%; border-collapse: collapse; background: #fff; }
td, th { border: 1px solid #ddd; padding: 6px 8px; text-align: left; font-size: 13px; }
.err { color: #c00; max-width: 260px; }
</style>
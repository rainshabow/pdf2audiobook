<script setup lang="ts">
import { useJobsStore } from "../stores/jobs";
import { useToastStore } from "../stores/toast";
import JobList from "../components/JobList.vue";
const jobs = useJobsStore();
const toast = useToastStore();
function refresh() {
  jobs.refresh();
  toast.show("已刷新");
}
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>任务中心</h1>
        <div class="page-sub">合成与改写并行执行；点击历史任务可跳转到对应章节</div>
      </div>
      <button class="btn btn-ghost btn-sm" @click="refresh">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-2.6-6.4M21 3v6h-6"/></svg>
        刷新
      </button>
    </div>
    <JobList />
  </div>
</template>

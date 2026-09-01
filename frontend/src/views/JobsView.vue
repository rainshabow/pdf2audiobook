<script setup lang="ts">
import { useJobsStore } from "../stores/jobs";
import JobList from "../components/JobList.vue";
const jobs = useJobsStore();
</script>

<template>
  <div>
    <h2>任务中心</h2>
    <button @click="jobs.refresh()">刷新</button>
    <JobList />
  </div>
</template>
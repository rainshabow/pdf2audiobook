import { defineStore } from "pinia";
import { ref } from "vue";
import * as api from "../api/client";

export const useJobsStore = defineStore("jobs", () => {
  const jobs = ref<api.JobInfo[]>([]);
  const active = ref(false);
  let timer: number | undefined;

  async function refresh() {
    jobs.value = await api.listJobs();
    active.value = jobs.value.some(
      (j) => j.status === "pending" || j.status === "running",
    );
    if (!active.value && timer !== undefined) {
      window.clearInterval(timer);
      timer = undefined;
    }
  }
  function startPolling() {
    if (timer !== undefined) return;
    void refresh();
    timer = window.setInterval(refresh, 2000);
  }
  async function cancel(id: string) {
    await api.cancelJob(id);
    await refresh();
  }
  async function resume(id: string) {
    const job = await api.resumeJob(id);
    await refresh();
    return job;
  }
  return { jobs, active, refresh, startPolling, cancel, resume };
});

import { listJobs } from "../api/client";

/**
 * 轮询等待任务结束：done/消失 → 正常返回；failed/cancelled → 抛错；超时 → 抛错。
 * @param jobId 任务 ID
 * @param timeoutMs 超时时间（默认 30 分钟）
 */
export async function waitForJob(
  jobId: string,
  timeoutMs = 30 * 60 * 1000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (true) {
    if (Date.now() >= deadline) {
      throw new Error("任务等待超时");
    }
    await new Promise((r) => setTimeout(r, 1500));
    const jobs = await listJobs();
    const cur = jobs.find((j) => j.id === jobId);
    if (!cur) return;
    if (cur.status === "done") return;
    if (cur.status === "failed" || cur.status === "cancelled") {
      throw new Error(cur.error ?? cur.status);
    }
  }
}

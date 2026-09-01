import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({
  listJobs: vi.fn(),
}));

import { listJobs } from "../api/client";
import type { JobInfo } from "../api/client";
import { waitForJob } from "./jobs";

function job(id: string, status: string, error: string | null = null): JobInfo {
  return {
    id, book_id: "b1", chapter_id: null, type: "parse",
    status, progress: status === "done" ? 1 : 0.5, error,
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
  };
}

describe("waitForJob", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
    vi.mocked(listJobs).mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("resolves when job reaches done", async () => {
    vi.mocked(listJobs).mockResolvedValueOnce([job("j1", "running")]);
    vi.mocked(listJobs).mockResolvedValue([job("j1", "done")]);
    const p = waitForJob("j1");
    await vi.advanceTimersByTimeAsync(1500);
    await vi.advanceTimersByTimeAsync(1500);
    await expect(p).resolves.toBeUndefined();
    expect(listJobs).toHaveBeenCalledTimes(2);
  });

  it("resolves when job disappears from the list", async () => {
    vi.mocked(listJobs).mockResolvedValue([]);
    const p = waitForJob("j1");
    await vi.advanceTimersByTimeAsync(1500);
    await expect(p).resolves.toBeUndefined();
  });

  it.each([
    ["failed", "boom"],
    ["cancelled", "取消"],
  ])("rejects with job error when status is %s", async (status, err) => {
    vi.mocked(listJobs).mockResolvedValue([job("j1", status, err)]);
    const p = waitForJob("j1");
    const caught = p.then(() => null, (e) => e); // 提前挂 handler，避免未处理拒绝告警
    await vi.advanceTimersByTimeAsync(1500);
    const errObj = await caught;
    expect(errObj).toBeInstanceOf(Error);
    expect((errObj as Error).message).toBe(err);
  });

  it("rejects with job status when failed and error is null", async () => {
    vi.mocked(listJobs).mockResolvedValue([job("j1", "failed", null)]);
    const p = waitForJob("j1");
    const caught = p.then(() => null, (e) => e);
    await vi.advanceTimersByTimeAsync(1500);
    const errObj = await caught;
    expect(errObj).toBeInstanceOf(Error);
    expect((errObj as Error).message).toBe("failed");
  });

  it("rejects with 任务等待超时 when timeout is exceeded", async () => {
    vi.mocked(listJobs).mockResolvedValue([job("j1", "running")]);
    const p = waitForJob("j1", 3000);
    const caught = p.then(() => null, (e) => e);
    await vi.advanceTimersByTimeAsync(1500);
    await vi.advanceTimersByTimeAsync(1500);
    const errObj = await caught;
    expect(errObj).toBeInstanceOf(Error);
    expect((errObj as Error).message).toBe("任务等待超时");
  });
});

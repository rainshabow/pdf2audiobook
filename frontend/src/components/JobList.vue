<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";
import { useJobsStore } from "../stores/jobs";
import type { JobInfo } from "../api/client";

const jobs = useJobsStore();
const router = useRouter();

const typeText: Record<string, string> = { parse: "解析", rewrite: "改写", synthesize: "合成", rebuild: "重建" };
const typeCls: Record<string, string> = { parse: "parse", rewrite: "rewrite", synthesize: "synth", rebuild: "synth" };
const statusText: Record<string, string> = { pending: "排队中", running: "进行中", done: "完成", failed: "失败", cancelled: "已取消" };

const running = computed(() => jobs.jobs.filter((j) => j.status === "running" || j.status === "pending"));
const history = computed(() => jobs.jobs.filter((j) => !["running", "pending"].includes(j.status)));

function go(j: JobInfo) {
  if (j.status === "running" || j.status === "pending") return; // 进行中不可跳转，避免误触
  if (j.chapter_id) router.push(`/books/${j.book_id}/chapters/${j.chapter_id}`);
  else router.push(`/books/${j.book_id}`);
}
</script>

<template>
  <div>
    <div v-if="running.length" class="job-group">
      <div class="section-title">进行中 <span class="muted" style="font-weight:400;font-size:13px">· 合成与改写互不阻塞</span></div>
      <div v-for="j in running" :key="j.id" class="job-card">
        <span class="job-type" :class="typeCls[j.type]">{{ typeText[j.type] ?? j.type }}</span>
        <div class="job-main">
          <div class="job-title">
            {{ typeText[j.type] ?? j.type }} · <span class="muted">{{ j.book_id.slice(0, 8) }}</span>
            <span v-if="j.chapter_id" class="muted">› {{ j.chapter_id }}</span>
            <span class="badge run"><span class="bdot"></span>{{ statusText[j.status] ?? j.status }}</span>
          </div>
          <div class="job-sub">{{ j.status === "pending" ? "排队等待中" : "处理中，可随时取消" }}</div>
        </div>
        <div class="job-right">
          <div class="progress" style="width:150px"><div class="bar" :style="{ width: `${Math.round(j.progress * 100)}%` }"></div></div>
          <span class="pct">{{ Math.round(j.progress * 100) }}%</span>
          <button class="btn btn-danger-ghost btn-sm" @click="jobs.cancel(j.id)">取消</button>
        </div>
      </div>
    </div>

    <div class="job-group">
      <div class="section-title">最近任务 <span class="muted" style="font-weight:400;font-size:13px">· 点击可跳转到对应书籍/章节</span></div>
      <div v-if="history.length">
        <div v-for="j in history" :key="j.id" class="job-card history" @click="go(j)">
          <span class="job-type" :class="typeCls[j.type]">{{ typeText[j.type] ?? j.type }}</span>
          <div class="job-main">
            <div class="job-title">
              {{ typeText[j.type] ?? j.type }} · <span class="muted">{{ j.book_id.slice(0, 8) }}</span>
              <span v-if="j.chapter_id" class="muted">› {{ j.chapter_id }}</span>
              <span class="badge" :class="j.status === 'failed' ? 'err' : j.status === 'cancelled' ? 'wait' : 'ok'">
                <span class="bdot"></span>{{ statusText[j.status] ?? j.status }}
              </span>
            </div>
            <div class="job-sub err" v-if="j.error">{{ j.error }}</div>
            <div class="job-sub" v-else>完成于 {{ new Date(j.updated_at).toLocaleString() }}</div>
          </div>
          <span class="job-arrow">→</span>
        </div>
      </div>
      <div v-else class="card empty"><div class="big">🗂</div>暂无历史任务</div>
    </div>
  </div>
</template>

<style scoped>
.job-group{margin-bottom:26px}
.job-card{display:flex;align-items:center;gap:14px;background:var(--surface);border:1px solid var(--line);border-radius:var(--r-md);padding:13px 16px;box-shadow:var(--shadow-sm);margin-bottom:10px;animation:fadeUp .35s var(--ease) both}
.job-card.history{cursor:pointer;transition:transform .18s var(--ease),box-shadow .18s,border-color .18s}
.job-card.history:hover{transform:translateY(-2px);box-shadow:var(--shadow-md);border-color:var(--green-200)}
@keyframes fadeUp{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.job-type{width:44px;height:44px;border-radius:13px;display:grid;place-items:center;font-size:12px;font-weight:700;color:#fff;flex:none}
.job-type.parse{background:#94A3B8}.job-type.rewrite{background:var(--green-500)}.job-type.synth{background:var(--green-700)}
.job-main{flex:1;min-width:0}
.job-title{font-weight:600;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.job-sub{color:var(--muted);font-size:12px;margin-top:4px;word-break:break-all}
.job-right{display:flex;align-items:center;gap:12px}
.pct{font-variant-numeric:tabular-nums;font-weight:700;font-size:13px;color:var(--green-700);min-width:38px;text-align:right}
.job-arrow{color:var(--faint);font-size:18px;transition:.18s;opacity:0;transform:translateX(-4px)}
.job-card.history:hover .job-arrow{opacity:1;transform:none}
</style>

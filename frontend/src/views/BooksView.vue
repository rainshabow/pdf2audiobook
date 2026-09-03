<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import * as api from "../api/client";
import { useBooksStore } from "../stores/books";
import { useToastStore } from "../stores/toast";
import UploadCard from "../components/UploadCard.vue";

const books = useBooksStore();
const router = useRouter();
const toast = useToastStore();
onMounted(() => books.refreshBooks());

const STATUS: Record<string, [string, string]> = {
  uploaded: ["待解析", "wait"],
  parsed: ["待改写", "wait"],
  rewriting: ["改写中", "run"],
  synthesizing: ["合成中", "run"],
  done: ["已完成", "ok"],
  failed: ["失败", "err"],
};
async function removeBook(b: api.Book) {
  if (!confirm(`删除《${b.title}》？`)) return;
  await books.remove(b.book_id);
  toast.show("已删除");
}
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>书架</h1>
        <div class="page-sub">导入 PDF，自动转成可听的章节与字幕</div>
      </div>
    </div>

    <UploadCard />

    <div class="section-title" style="margin-top:26px">
      我的书籍 <span class="muted" style="font-weight:400;font-size:13px">· 点击卡片进入工作台</span>
    </div>

    <div v-if="books.books.length" class="books-grid">
      <div v-for="(b, i) in books.books" :key="b.book_id" class="book-card"
           :style="{ animationDelay: `${i * 60}ms` }" @click="router.push(`/books/${b.book_id}`)">
        <div class="book-cover">
          <span class="cover-letter">{{ b.title.slice(0, 1) }}</span>
          <span class="cover-meta">{{ b.chapter_count }} 章 · {{ b.page_count }} 页</span>
          <button class="card-del" title="删除书籍" @click.stop="removeBook(b)">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M8 6V4h8v2m-9 0 1 14h8l1-14"/></svg>
          </button>
        </div>
        <div class="book-body">
          <div class="book-title">{{ b.title }}</div>
          <div class="book-meta">{{ b.page_count }} 页 · {{ b.chapter_count }} 章</div>
          <div class="book-foot">
            <span class="badge" :class="`${STATUS[b.status]?.[1] ?? 'wait'}`">
              <span class="bdot"></span>{{ STATUS[b.status]?.[0] ?? b.status }}
            </span>
            <span class="go">进入工作台 →</span>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="card empty">
      <div class="big">📚</div>
      <p>还没有书籍，先上传一本 PDF 吧</p>
    </div>
  </div>
</template>

<style scoped>
.books-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:18px;margin-top:6px}
.book-card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);overflow:hidden;cursor:pointer;box-shadow:var(--shadow-sm);transition:transform .2s var(--ease),box-shadow .2s var(--ease),border-color .2s;animation:fadeUp .4s var(--ease) both}
.book-card:hover{transform:translateY(-4px);box-shadow:var(--shadow-lg);border-color:var(--green-100)}
@keyframes fadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.book-cover{height:82px;background:linear-gradient(120deg,var(--green-500),var(--green-700));position:relative;display:flex;align-items:flex-end;gap:10px;padding:0 16px 12px;color:#fff;overflow:hidden}
.book-cover::after{content:"";position:absolute;right:-20px;top:-30px;width:120px;height:120px;border-radius:50%;background:rgba(255,255,255,.08)}
.cover-letter{font-size:30px;font-weight:800;text-shadow:0 2px 12px rgba(0,0,0,.18)}
.cover-meta{font-size:12px;opacity:.9;padding-bottom:5px}
.card-del{position:absolute;right:10px;top:10px;width:28px;height:28px;border-radius:9px;display:grid;place-items:center;color:#fff;background:rgba(0,0,0,.16);opacity:0;transition:.18s}
.book-card:hover .card-del{opacity:1}
.card-del:hover{background:rgba(220,38,38,.85)}
.book-body{padding:13px 16px 15px}
.book-title{font-weight:700;font-size:15px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.book-meta{color:var(--muted);font-size:12px;margin-top:4px}
.book-foot{display:flex;align-items:center;justify-content:space-between;margin-top:12px}
.go{font-size:12px;color:var(--green-600);font-weight:600;opacity:0;transform:translateX(-4px);transition:.2s var(--ease)}
.book-card:hover .go{opacity:1;transform:none}
</style>

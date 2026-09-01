<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { useBooksStore } from "../stores/books";
import UploadCard from "../components/UploadCard.vue";

const books = useBooksStore();
const router = useRouter();
onMounted(() => books.refreshBooks());
</script>

<template>
  <div>
    <UploadCard />
    <h2>书架（{{ books.books.length }}）</h2>
    <ul class="books">
      <li v-for="b in books.books" :key="b.book_id">
        <button class="link" @click="router.push(`/books/${b.book_id}`)">{{ b.title }}</button>
        <span>{{ b.page_count }} 页 · {{ b.chapter_count }} 章 · {{ b.status }}</span>
        <button @click="books.remove(b.book_id)">删除</button>
      </li>
    </ul>
    <p v-if="!books.books.length" class="empty">还没有书籍，先上传一本 PDF 吧。</p>
  </div>
</template>

<style scoped>
.books { list-style: none; padding: 0; }
.books li { display: flex; gap: 12px; align-items: center; padding: 8px; background: #fff; margin-bottom: 6px; border-radius: 6px; }
.link { background: none; border: none; color: #06c; font-size: 15px; font-weight: 600; cursor: pointer; flex: 1; text-align: left; }
.empty { color: #888; }
</style>
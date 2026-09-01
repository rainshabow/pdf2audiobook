<script setup lang="ts">
import { ref } from "vue";
import { useBooksStore } from "../stores/books";

const books = useBooksStore();
const uploading = ref(false);
const error = ref("");

async function onFile(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  uploading.value = true;
  error.value = "";
  try {
    await books.upload(file);
  } catch (err: any) {
    error.value = err?.response?.data?.detail ?? String(err);
  } finally {
    uploading.value = false;
    input.value = "";
  }
}
</script>

<template>
  <div class="upload-card">
    <h2>上传 PDF 书籍</h2>
    <input type="file" accept="application/pdf" @change="onFile" :disabled="uploading" />
    <span v-if="uploading">上传中…</span>
    <p v-if="error" class="err">{{ error }}</p>
  </div>
</template>

<style scoped>
.upload-card { border: 1px dashed #aaa; padding: 20px; border-radius: 8px; background: #fff; }
.err { color: #c00; }
</style>
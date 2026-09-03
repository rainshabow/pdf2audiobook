<script setup lang="ts">
import { ref } from "vue";
import { useBooksStore } from "../stores/books";
import { useToastStore } from "../stores/toast";

const books = useBooksStore();
const toast = useToastStore();
const uploading = ref(false);
const error = ref("");
const drag = ref(false);

async function onFile(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  await upload(file);
  input.value = "";
}
async function upload(file: File) {
  uploading.value = true;
  error.value = "";
  try {
    await books.upload(file);
    toast.show(`已导入《${file.name.replace(/\.pdf$/i, "")}》，开始解析`);
  } catch (err: any) {
    error.value = err?.response?.data?.detail ?? String(err);
  } finally {
    uploading.value = false;
  }
}
function onDrop(e: DragEvent) {
  drag.value = false;
  const file = e.dataTransfer?.files?.[0];
  if (file) void upload(file);
}
</script>

<template>
  <div>
    <div class="upload-zone" :class="{ drag }"
         @dragover.prevent="drag = true" @dragleave.prevent="drag = false"
         @drop.prevent="onDrop" @click="($refs.file as HTMLInputElement)?.click()">
      <div class="up-icon">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/></svg>
      </div>
      <div class="up-title">{{ uploading ? "正在上传…" : drag ? "松开导入 PDF" : "拖入 PDF，或点击选择文件" }}</div>
      <div class="muted up-sub">解析章节 → 口语化改写 → 分章合成语音与字幕</div>
      <input ref="file" type="file" accept="application/pdf" class="hidden-input"
             :disabled="uploading" @change="onFile" />
    </div>
    <p v-if="error" class="err" style="margin-top:8px">上传失败：{{ error }}</p>
  </div>
</template>

<style scoped>
.upload-zone{border:2px dashed var(--green-200);border-radius:var(--r-lg);padding:26px 20px;text-align:center;background:linear-gradient(180deg,#fff,var(--green-50));transition:border-color .2s,background .2s,transform .2s,box-shadow .2s;cursor:pointer;position:relative}
.upload-zone:hover,.upload-zone.drag{border-color:var(--green-500);background:#fff;transform:translateY(-2px);box-shadow:var(--shadow-md)}
.up-icon{width:52px;height:52px;margin:0 auto 10px;border-radius:16px;background:var(--green-100);color:var(--green-700);display:grid;place-items:center;animation:floaty 3s ease-in-out infinite}
.up-title{font-weight:700;font-size:15px}
.up-sub{margin-top:5px;font-size:12px}
.hidden-input{display:none}
</style>

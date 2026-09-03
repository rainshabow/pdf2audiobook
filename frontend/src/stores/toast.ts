import { defineStore } from "pinia";
import { ref } from "vue";

export interface ToastItem { id: number; text: string; ok: boolean; }

export const useToastStore = defineStore("toast", () => {
  const items = ref<ToastItem[]>([]);
  let seed = 0;
  function show(text: string, ok = true) {
    const id = ++seed;
    items.value.push({ id, text, ok });
    window.setTimeout(() => dismiss(id), 2400);
  }
  function dismiss(id: number) {
    items.value = items.value.filter((t) => t.id !== id);
  }
  return { items, show, dismiss };
});

import { defineStore } from "pinia";
import { ref } from "vue";
import * as api from "../api/client";

export const useBooksStore = defineStore("books", () => {
  const books = ref<api.Book[]>([]);
  const detail = ref<api.BookDetail | null>(null);

  async function refreshBooks() {
    books.value = await api.listBooks();
  }
  async function loadBook(id: string) {
    detail.value = await api.getBook(id);
  }
  async function upload(file: File) {
    const b = await api.uploadBook(file);
    await refreshBooks();
    return b;
  }
  async function remove(id: string) {
    await api.deleteBook(id);
    if (detail.value?.book_id === id) detail.value = null;
    await refreshBooks();
  }
  return { books, detail, refreshBooks, loadBook, upload, remove };
});

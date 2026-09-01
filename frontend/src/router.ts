import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: () => import("./views/BooksView.vue") },
    { path: "/books/:bookId", component: () => import("./views/BookDetailView.vue") },
    { path: "/books/:bookId/chapters/:chapterId", component: () => import("./views/ChapterView.vue") },
    { path: "/jobs", component: () => import("./views/JobsView.vue") },
    { path: "/settings", component: () => import("./views/SettingsView.vue") },
  ],
});

export default router;

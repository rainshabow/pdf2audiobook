import axios from "axios";

export interface Book {
  book_id: string; title: string; author: string; page_count: number;
  created_at: string; status: string; chapter_count: number;
}
export interface ChapterInfo {
  id: string; title: string; level: number; page_start: number; page_end: number;
  char_count: number; status: string; audio_duration: number;
}
export interface BookDetail extends Book {
  chapters: ChapterInfo[];
  toc: Array<{ level: number; title: string; page: number }>;
}
export interface JobInfo {
  id: string; book_id: string; chapter_id: string | null; type: string;
  status: string; progress: number; error: string | null;
  created_at: string; updated_at: string;
}
export interface SettingsView {
  tts_engine: string; tts_model: string; tts_speaker: string | null;
  tts_speed: number; tts_instruct: string | null; llm_model: string;
  chapter_low_chars: number; chapter_high_chars: number;
}

const api = axios.create({ baseURL: "/api" });

export async function listBooks(): Promise<Book[]> {
  return (await api.get("/books")).data;
}
export async function uploadBook(file: File): Promise<Book> {
  const fd = new FormData();
  fd.append("file", file);
  return (await api.post("/books", fd)).data;
}
export async function getBook(id: string): Promise<BookDetail> {
  return (await api.get(`/books/${id}`)).data;
}
export async function deleteBook(id: string): Promise<void> {
  await api.delete(`/books/${id}`);
}
export async function startJob(
  bookId: string, type: "parse" | "rewrite" | "synthesize",
): Promise<JobInfo> {
  return (await api.post(`/books/${bookId}/${type}`)).data;
}
export async function getSpeechMd(bookId: string, ch: string): Promise<string> {
  return (await api.get(`/books/${bookId}/chapters/${ch}/speech.md`)).data;
}
export async function saveSpeechMd(bookId: string, ch: string, text: string): Promise<void> {
  await api.put(`/books/${bookId}/chapters/${ch}/speech.md`, text,
    { headers: { "Content-Type": "text/plain" } });
}
export async function rebuildChapter(bookId: string, ch: string): Promise<JobInfo> {
  return (await api.post(`/books/${bookId}/chapters/${ch}/rebuild`)).data;
}
export async function rewriteChapter(bookId: string, ch: string): Promise<JobInfo> {
  return (await api.post(`/books/${bookId}/chapters/${ch}/rewrite`)).data;
}
export const audioUrl = (bookId: string, ch: string) =>
  `/api/books/${bookId}/chapters/${ch}/audio`;
export const vttUrl = (bookId: string, ch: string) =>
  `/api/books/${bookId}/chapters/${ch}/chapter.vtt`;
export async function listJobs(): Promise<JobInfo[]> {
  return (await api.get("/jobs")).data;
}
export async function cancelJob(id: string): Promise<void> {
  await api.post(`/jobs/${id}/cancel`);
}
export async function getSettings(): Promise<SettingsView> {
  return (await api.get("/settings")).data;
}
export async function saveSettings(s: SettingsView): Promise<SettingsView> {
  return (await api.put("/settings", s)).data;
}
export async function listTTSModels(): Promise<Array<{ name: string; type: string }>> {
  return (await api.get("/tts/models")).data;
}
export async function listTTSSpeakers(): Promise<Array<{ name: string }>> {
  return (await api.get("/tts/speakers")).data;
}

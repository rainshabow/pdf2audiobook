import { describe, expect, it, vi } from "vitest";

vi.mock("axios", () => {
  const data = { data: [{ book_id: "b1", title: "测试", chapter_count: 0 }] };
  return { default: { create: () => ({ get: vi.fn(async () => data), post: vi.fn(async () => data), put: vi.fn(async () => data), delete: vi.fn(async () => ({ data: {} })) }) } };
});

import * as api from "./client";

describe("api client", () => {
  it("listBooks returns books", async () => {
    const books = await api.listBooks();
    expect(books).toEqual([{ book_id: "b1", title: "测试", chapter_count: 0 }]);
  });
  it("audioUrl/vttUrl build paths", () => {
    expect(api.audioUrl("b1", "ch-001")).toBe("/api/books/b1/chapters/ch-001/audio");
    expect(api.vttUrl("b1", "ch-001")).toBe("/api/books/b1/chapters/ch-001/chapter.vtt");
  });
});

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";
import { EditorView, basicSetup } from "codemirror";
import { markdown } from "@codemirror/lang-markdown";
import { marked } from "marked";

const props = defineProps<{ modelValue: string }>();
const html = computed(() => marked.parse(props.modelValue) as string);
const emit = defineEmits<{ (e: "update:modelValue", v: string): void }>();
const host = ref<HTMLElement | null>(null);
const preview = ref(false);
const view = shallowRef<EditorView | null>(null);

watch(() => props.modelValue, (v) => {
  const editor = view.value;
  if (!editor) return;
  const cur = editor.state.doc.toString();
  if (v !== cur) editor.dispatch({ changes: { from: 0, to: cur.length, insert: v } });
});

onMounted(() => {
  if (!host.value) return;
  view.value = new EditorView({
    doc: props.modelValue,
    extensions: [basicSetup, markdown(),
      EditorView.updateListener.of((u) => {
        if (u.docChanged) emit("update:modelValue", u.state.doc.toString());
      })],
    parent: host.value,
  });
});
onBeforeUnmount(() => view.value?.destroy());
</script>

<template>
  <div class="editor">
    <label><input type="checkbox" v-model="preview" /> 预览</label>
    <div v-show="!preview" ref="host" class="cm"></div>
    <div v-show="preview" class="preview" v-html="html"></div>
  </div>
</template>

<style scoped>
.editor :deep(.cm-editor){height:460px;border:1px solid var(--line);border-radius:var(--r-md);overflow:hidden;font-size:14px}
.editor :deep(.cm-scroller){font-family:var(--font);line-height:1.9}
.tool{display:flex;align-items:center;justify-content:flex-end;gap:10px;margin-bottom:10px;font-size:13px;color:var(--muted)}
.cm { border:1px solid var(--line); border-radius:var(--r-md); height:460px; overflow:auto; background:#fff; }
.preview { border:1px solid var(--line); border-radius:var(--r-md); padding:18px; height:460px; overflow:auto; background:#fff; line-height:1.9; }
.preview :deep(h1),.preview h1,.preview h2,.preview h3{margin:12px 0 6px;line-height:1.5}
.preview p{margin-bottom:10px}
</style>
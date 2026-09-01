<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from "vue";
import { EditorView, basicSetup } from "codemirror";
import { markdown } from "@codemirror/lang-markdown";
import { marked } from "marked";

const props = defineProps<{ modelValue: string }>();
const html = computed(() => marked.parse(props.modelValue) as string);
const emit = defineEmits<{ (e: "update:modelValue", v: string): void }>();
const host = ref<HTMLElement | null>(null);
const preview = ref(false);
const view = shallowRef<EditorView | null>(null);

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
.cm { border: 1px solid #ddd; height: 60vh; overflow: auto; }
.preview { border: 1px solid #ddd; padding: 16px; height: 60vh; overflow: auto; background: #fff; }
</style>
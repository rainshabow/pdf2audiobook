<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import * as api from "../api/client";
import { useSettingsStore } from "../stores/settings";

const store = useSettingsStore();
const form = reactive<api.SettingsView>({
  tts_engine: "mock", tts_model: "", tts_speaker: null, tts_speed: 1,
  tts_instruct: null, llm_model: "dsv4-flash",
  chapter_low_chars: 5000, chapter_high_chars: 15000,
});
const models = ref<Array<{ name: string; type: string }>>([]);
const speakers = ref<Array<{ name: string }>>([]);
const saved = ref(false);

onMounted(async () => {
  await store.load();
  if (store.settings) Object.assign(form, store.settings);
  await refreshLists();
});
async function refreshLists() {
  try {
    models.value = await api.listTTSModels();
    speakers.value = await api.listTTSSpeakers();
  } catch { /* 引擎未启动时忽略 */ }
}
async function save() {
  await store.save({ ...form });
  saved.value = true;
  setTimeout(() => (saved.value = false), 2000);
}
</script>

<template>
  <div>
    <h2>设置</h2>
    <label>TTS 引擎
      <select v-model="form.tts_engine" @change="refreshLists">
        <option value="mock">mock（测试）</option>
        <option value="qwen_webui">qwen_webui（本机 Qwen3-TTS）</option>
      </select>
    </label>
    <label>模型
      <select v-model="form.tts_model">
        <option v-for="m in models" :key="m.name" :value="m.name">{{ m.name }}</option>
      </select>
    </label>
    <label>声音
      <select v-model="form.tts_speaker">
        <option :value="null">默认</option>
        <option v-for="s in speakers" :key="s.name" :value="s.name">{{ s.name }}</option>
      </select>
    </label>
    <label>固化语速
      <input type="number" v-model.number="form.tts_speed" step="0.1" min="0.5" max="2" />
    </label>
    <label>朗读指示
      <input v-model="form.tts_instruct" placeholder="如：用温柔的语气说" />
    </label>
    <label>LLM 模型
      <input v-model="form.llm_model" />
    </label>
    <label>章节字数下限 <input type="number" v-model.number="form.chapter_low_chars" /></label>
    <label>章节字数上限 <input type="number" v-model.number="form.chapter_high_chars" /></label>
    <button @click="save">保存设置</button>
    <span v-if="saved" class="ok">已保存</span>
  </div>
</template>

<style scoped>
label { display: block; margin-bottom: 10px; }
.ok { color: #080; margin-left: 8px; }
</style>
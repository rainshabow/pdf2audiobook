<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import * as api from "../api/client";
import { useSettingsStore } from "../stores/settings";

const store = useSettingsStore();
const form = reactive<api.SettingsView>({
  tts_engine: "mock", tts_model: "", tts_speaker: null, tts_speed: 1.25,
  tts_instruct: "用平稳、一致的叙述语气朗读，情绪保持中性稳定，前后句语气连贯。",
  llm_model: "deepseek-v4-flash",
  chapter_low_chars: 5000, chapter_high_chars: 15000,
  tts_mode: "custom", tts_clone_ref_audio: null, tts_clone_ref_text: null,
  tts_batch_size: 10, rewrite_concurrency: 20,
});
const models = ref<Array<{ name: string; type: string }>>([]);
const speakers = ref<Array<{ name: string }>>([]);
const saved = ref(false);
const listError = ref("");

onMounted(async () => {
  await store.load();
  if (store.settings) Object.assign(form, store.settings);
  await refreshLists();
});
async function onEngineChange() {
  // v-model 已将 form.tts_engine 更新为新值，这里无条件重置模型/声音，
  // 避免旧引擎的模型名或声音残留到新引擎。
  form.tts_model = "";
  form.tts_speaker = null;
  await refreshLists();
}
async function refreshLists() {
  try {
    models.value = await api.listTTSModels();
    speakers.value = await api.listTTSSpeakers();
    listError.value = "";
  } catch (e: any) {
    models.value = [];
    speakers.value = [];
    listError.value = "加载模型/声音列表失败: " + (e?.response?.data?.detail ?? String(e));
  }
}
async function onCloneAudio(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  listError.value = "";
  try {
    const res = await api.uploadCloneAudio(file);
    form.tts_clone_ref_audio = res.path;
  } catch (err: any) {
    listError.value = "上传克隆音频失败: " + (err?.response?.data?.detail ?? String(err));
  } finally {
    input.value = "";
  }
}
async function save() {
  listError.value = "";
  try {
    await store.save({ ...form });
    saved.value = true;
    setTimeout(() => (saved.value = false), 2000);
  } catch (e: any) {
    listError.value = "保存设置失败: " + (e?.response?.data?.detail ?? String(e));
  }
}
</script>

<template>
  <div>
    <h2>设置</h2>
    <label>TTS 引擎
      <select v-model="form.tts_engine" @change="onEngineChange">
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
    <label>合成模式
      <select v-model="form.tts_mode">
        <option value="custom">CustomVoice（选声音）</option>
        <option value="clone">Voice Clone（克隆音色）</option>
      </select>
    </label>
    <template v-if="form.tts_mode === 'clone'">
      <label>克隆参考音频
        <input type="file" accept="audio/wav,audio/mpeg,audio/*" @change="onCloneAudio" />
        <span v-if="form.tts_clone_ref_audio" class="ok">{{ form.tts_clone_ref_audio }}</span>
      </label>
      <label>参考音频文本（可选，留空则仅用音色向量）
        <input v-model="form.tts_clone_ref_text" placeholder="参考音频里说的内容" />
      </label>
    </template>
    <label>合成批处理句数
      <input type="number" v-model.number="form.tts_batch_size" min="1" max="50" />
    </label>
    <label>改写并发上限
      <input type="number" v-model.number="form.rewrite_concurrency" min="1" max="100" />
    </label>
    <label>固化语速（基础语速，默认 1.25）
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
    <p v-if="listError" class="err">{{ listError }}</p>
  </div>
</template>

<style scoped>
label { display: block; margin-bottom: 10px; }
.ok { color: #080; margin-left: 8px; }
.err { color: #c00; }
</style>
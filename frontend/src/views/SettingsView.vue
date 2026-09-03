<script setup lang="ts">
import { computed, onActivated, onDeactivated, onMounted, reactive, ref, watch } from "vue";
import { onBeforeRouteLeave } from "vue-router";
import * as api from "../api/client";
import { useSettingsStore } from "../stores/settings";

// KeepAlive 按组件名缓存本页（App.vue include="SettingsView"）
defineOptions({ name: "SettingsView" });

const store = useSettingsStore();
const form = reactive<api.SettingsView>({
  tts_engine: "mock", tts_model: "", tts_speaker: null, tts_speed: 1.25,
  tts_instruct: "用平稳、一致的叙述语气朗读，情绪保持中性稳定，前后句语气连贯。",
  llm_model: "deepseek-v4-flash",
  chapter_low_chars: 5000, chapter_high_chars: 15000,
  tts_mode: "custom", tts_clone_ref_audio: null, tts_clone_ref_text: null,
  tts_batch_size: 3, tts_concurrency: 2, rewrite_concurrency: 20,
});
const models = ref<Array<{ name: string; type: string }>>([]);
const speakers = ref<Array<{ name: string }>>([]);
const saved = ref(false);
const listError = ref("");
const hint = ref("");
const loadingModel = ref(false);
const engineRunning = ref(false);
const engineBusy = ref(false);
const previewBusy = ref<string | null>(null);
const dirty = ref(false);
let initialized = false;
let previewAudio: HTMLAudioElement | null = null;
let previewObjectUrl: string | null = null;

// 仅 qwen/mimo 的预置音色提供逐音色试听（voicedesign 无预置音色）
const canPreviewVoices = computed(() =>
  ["qwen_webui", "mimo"].includes(form.tts_engine)
  && form.tts_model !== "mimo-v2.5-tts-voicedesign"
  && speakers.value.length > 0);

function previewModelFor(engine: string): string {
  if (engine === "mimo") return "mimo-v2.5-tts"; // 预置音色仅属于该模型
  if (form.tts_model) return form.tts_model;
  return models.value[0]?.name ?? "";
}

async function previewVoice(voice: string) {
  if (previewBusy.value) return;
  listError.value = "";
  previewBusy.value = voice;
  try {
    const model = previewModelFor(form.tts_engine);
    if (!model) throw new Error("请先选择模型");
    const blob = await api.previewTTS(form.tts_engine, model, voice);
    if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
    previewObjectUrl = URL.createObjectURL(blob);
    if (previewAudio) {
      previewAudio.pause();
      previewAudio.src = "";
    }
    previewAudio = new Audio(previewObjectUrl);
    await previewAudio.play();
  } catch (e: any) {
    let detail = e?.response?.data?.detail ?? String(e);
    const data = e?.response?.data;
    if (data instanceof Blob) {
      try {
        const text = await data.text();
        try { detail = JSON.parse(text)?.detail ?? text; } catch { detail = text || detail; }
      } catch { /* 保持默认错误 */ }
    }
    listError.value = "试听失败: " + detail;
  } finally {
    previewBusy.value = null;
  }
}

onMounted(async () => {
  await store.load();
  if (store.settings) Object.assign(form, store.settings);
  initialized = true;
  await refreshLists();
  // 保存的模型不在当前引擎列表中（例如保存时为空）时自动选择首个模型
  if (models.value.length && !models.value.some(m => m.name === form.tts_model)) {
    form.tts_model = models.value[0].name;
  }
  await refreshEngineStatus();
});

// 表单发生任何修改都标记为未保存；离开页面时自动保存，返回时不再重新加载
watch(form, () => {
  if (initialized) dirty.value = true;
}, { deep: true });

onActivated(() => {
  // 回到设置页：不重载模型/音色列表，仅刷新引擎运行状态（或引擎列表为空时补一次）
  refreshEngineStatus();
  if (form.tts_engine === "qwen_webui" && !models.value.length) refreshLists();
});

onDeactivated(() => {
  // 离开页面时停止试听，避免 KeepAlive 缓存后声音在后台继续播放
  if (previewAudio) {
    previewAudio.pause();
    previewAudio.src = "";
    previewAudio = null;
  }
  if (previewObjectUrl) {
    URL.revokeObjectURL(previewObjectUrl);
    previewObjectUrl = null;
  }
});

onBeforeRouteLeave(async () => {
  // 未点“保存设置”直接离开时自动落盘，避免返回后看到“设置被重新加载”的假象
  if (dirty.value) {
    try {
      await save(false);
    } catch { /* 保存失败不阻塞离开，错误已展示在页面 */ }
  }
});
async function onEngineChange() {
  // v-model 已将 form.tts_engine 更新为新值，这里无条件重置模型/声音，
  // 避免旧引擎的模型名或声音残留到新引擎。
  form.tts_model = "";
  form.tts_speaker = null;
  await refreshLists();
  // 新引擎自动选择首个模型，避免空模型（mimo 首项即 mimo-v2.5-tts）
  if (!form.tts_model && models.value.length > 0) {
    form.tts_model = models.value[0].name;
  }
}
async function refreshLists() {
  try {
    models.value = await api.listTTSModels(form.tts_engine);
    speakers.value = await api.listTTSSpeakers(form.tts_engine);
    listError.value = "";
    hint.value = "";
    if (form.tts_engine === "qwen_webui" && (!models.value.length || !speakers.value.length)) {
      hint.value = "引擎模型尚未加载：请点击上方「加载模型」；若仍为空请确认 qwen-tts-webui 已启动。";
    }
  } catch (e: any) {
    models.value = [];
    speakers.value = [];
    listError.value = "加载模型/声音列表失败: " + (e?.response?.data?.detail ?? String(e));
  }
}
async function refreshEngineStatus() {
  try {
    const st = await api.ttsServiceStatus();
    engineRunning.value = st.running;
  } catch { engineRunning.value = false; }
}
async function startEngine() {
  engineBusy.value = true;
  listError.value = "";
  try {
    await api.ttsServiceStart();
    await refreshEngineStatus();
    await refreshLists();
  } catch (e: any) {
    listError.value = "启动引擎失败: " + (e?.response?.data?.detail ?? String(e));
  } finally {
    engineBusy.value = false;
  }
}
async function stopEngine() {
  if (!window.confirm("确定停止 qwen 引擎服务吗？")) return;
  engineBusy.value = true;
  listError.value = "";
  try {
    await api.ttsServiceStop();
    await refreshEngineStatus();
    models.value = [];
    speakers.value = [];
    hint.value = "引擎已停止。需要时点击「启动服务」。";
  } catch (e: any) {
    listError.value = "停止引擎失败: " + (e?.response?.data?.detail ?? String(e));
  } finally {
    engineBusy.value = false;
  }
}
async function loadModel() {
  loadingModel.value = true;
  listError.value = "";
  hint.value = "";
  try {
    await api.loadTTSModel();
    await refreshLists();
  } catch (e: any) {
    listError.value = "加载模型失败: " + (e?.response?.data?.detail ?? String(e));
  } finally {
    loadingModel.value = false;
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
async function save(flash = true) {
  listError.value = "";
  try {
    await store.save({ ...form });
    dirty.value = false;
    if (flash) {
      saved.value = true;
      setTimeout(() => (saved.value = false), 2000);
    }
  } catch (e: any) {
    listError.value = "保存设置失败: " + (e?.response?.data?.detail ?? String(e));
    throw e;
  }
}
</script>
<template>
  <div>
    <div class="page-head">
      <div>
        <h1>设置</h1>
        <div class="page-sub">所有修改会在离开页面时自动保存 · 绿色状态点为运行中</div>
      </div>
      <div class="row">
        <button class="btn btn-primary btn-sm" @click="save()">保存设置</button>
        <span v-if="saved" class="badge ok"><span class="bdot"></span>已保存</span>
      </div>
    </div>

    <div v-if="hint" class="hint" style="margin-bottom:14px">{{ hint }}</div>
    <p v-if="listError" class="err" style="margin-bottom:12px">{{ listError }}</p>

    <div class="settings-grid">
      <!-- 引擎 -->
      <div class="set-group" style="grid-column:1 / -1">
        <div class="panel-title" style="margin:0 0 14px">TTS 引擎</div>
        <div class="engine-wrap">
          <label class="field wide">引擎
            <select v-model="form.tts_engine" @change="onEngineChange">
              <option value="mock">mock（测试）</option>
              <option value="qwen_webui">qwen_webui（本机 Qwen3-TTS）</option>
              <option value="mimo">mimo（云端 MiMo-TTS 2.5）</option>
            </select>
          </label>
          <label class="field wide">模型
            <select v-model="form.tts_model">
              <option v-for="m in models" :key="m.name" :value="m.name">{{ m.name }}</option>
            </select>
          </label>
        </div>

        <div v-if="form.tts_engine === 'qwen_webui'" class="engine-actions">
          <button class="btn btn-soft btn-sm" :disabled="engineBusy" @click="startEngine">启动服务</button>
          <button class="btn btn-ghost btn-sm" :disabled="engineBusy" @click="stopEngine">停止服务</button>
          <button class="btn btn-ghost btn-sm" :disabled="engineBusy || !engineRunning" @click="loadModel">
            {{ loadingModel ? "加载中…" : "加载模型" }}
          </button>
          <span class="dot" :data-on="engineRunning"></span>
          <span class="tip">{{ engineRunning ? "引擎运行中" : "引擎未运行" }} · 首次使用需加载模型（数十秒）</span>
        </div>
        <p v-else-if="form.tts_engine === 'mimo'" class="hint">云端 MiMo-TTS：模型/音色保存后即可使用；克隆模式自动使用 mimo-v2.5-tts-voiceclone。</p>

        <label v-if="form.tts_model !== 'mimo-v2.5-tts-voicedesign'" class="field" style="margin-top:12px">当前声音
          <select v-model="form.tts_speaker">
            <option :value="null">默认</option>
            <option v-for="s in speakers" :key="s.name" :value="s.name">{{ s.name }}</option>
          </select>
        </label>

        <div v-if="canPreviewVoices" class="voice-block">
          <div class="muted" style="font-size:12px;margin-bottom:8px">音色试听（你好，世界）——点击名称选中，点 ▶ 试听</div>
          <div class="voice-grid">
            <div v-for="s in speakers" :key="s.name" class="voice-chip"
                 :class="{ sel: form.tts_speaker === s.name, playing: previewBusy === s.name }"
                 @click="form.tts_speaker = s.name">
              <span class="voice-name">{{ s.name }}</span>
              <button class="play-mini" type="button" :disabled="previewBusy !== null && previewBusy !== s.name"
                      @click.stop="previewVoice(s.name)">
                <template v-if="previewBusy === s.name">
                  <span class="eq"><i></i><i></i><i></i></span>
                </template>
                <template v-else>▶</template>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 合成 -->
      <div class="set-group">
        <div class="panel-title">合成</div>
        <label class="field">合成模式
          <select v-model="form.tts_mode">
            <option value="custom">CustomVoice（选声音）</option>
            <option value="clone">Voice Clone（克隆音色）</option>
          </select>
        </label>
        <template v-if="form.tts_mode === 'clone'">
          <label class="field">克隆参考音频
            <input type="file" accept="audio/wav,audio/mpeg,audio/*" @change="onCloneAudio" />
            <span v-if="form.tts_clone_ref_audio" class="ok">{{ form.tts_clone_ref_audio }}</span>
          </label>
          <label class="field">参考音频文本（可选）
            <input v-model="form.tts_clone_ref_text" placeholder="参考音频里说的内容" />
          </label>
        </template>
        <label class="field">批处理句数（建议 1–5）
          <input type="number" v-model.number="form.tts_batch_size" min="1" max="50" />
        </label>
        <label class="field">合成并发上限（本机 1–2，云端可大）
          <input type="number" v-model.number="form.tts_concurrency" min="1" max="32" />
        </label>
        <label class="field">固化语速（默认 1.25）
          <input type="number" v-model.number="form.tts_speed" step="0.1" min="0.5" max="2" />
        </label>
        <label class="field">朗读指示<template v-if="form.tts_engine === 'mimo' && form.tts_model === 'mimo-v2.5-tts-voicedesign'">（voicedesign 下为音色设计描述）</template>
          <input v-model="form.tts_instruct" placeholder="如：用温柔的语气说" />
        </label>
      </div>

      <!-- 改写 -->
      <div class="set-group">
        <div class="panel-title">改写</div>
        <label class="field">LLM 模型
          <input v-model="form.llm_model" />
        </label>
        <label class="field">改写并发上限
          <input type="number" v-model.number="form.rewrite_concurrency" min="1" max="100" />
        </label>
        <div class="static-row">
          <span><b>缩写朗读预处理</b><small>LLM → L L M，白名单/长词放行</small></span>
          <span class="badge ok"><span class="bdot"></span>已开启</span>
        </div>
      </div>

      <!-- 章节 -->
      <div class="set-group">
        <div class="panel-title">章节规则</div>
        <label class="field">章节字数下限
          <input type="number" v-model.number="form.chapter_low_chars" />
        </label>
        <label class="field">章节字数上限
          <input type="number" v-model.number="form.chapter_high_chars" />
        </label>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;align-items:start}
.set-group{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);padding:18px;box-shadow:var(--shadow-sm)}
.engine-wrap{display:grid;grid-template-columns:1fr 1.6fr;gap:14px}
.field{font-size:12.5px;color:var(--muted);margin-bottom:10px}
.field small{display:block;color:var(--faint);margin-top:2px}
.field select,.field input{display:block;width:100%;margin-top:6px}
.engine-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0 0}
.voice-block{margin-top:14px;padding-top:14px;border-top:1px dashed var(--line)}
.voice-grid{display:flex;flex-wrap:wrap;gap:8px}
.voice-chip{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:20px;padding:5px 6px 5px 13px;background:#fff;transition:.18s;cursor:pointer}
.voice-chip:hover{border-color:var(--green-200);background:var(--green-50)}
.voice-chip.sel{border-color:var(--green-500);background:var(--green-50)}
.voice-chip.playing{border-color:var(--green-500);box-shadow:0 0 0 3px rgba(16,185,129,.14)}
.voice-name{font-size:13px;font-weight:600}
.play-mini{width:28px;height:28px;border-radius:50%;background:var(--green-100);color:var(--green-700);display:grid;place-items:center;transition:.18s;font-size:12px}
.play-mini:hover:not(:disabled){background:var(--green-600);color:#fff}
.play-mini:disabled{opacity:.6;cursor:default}
.static-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 0;border-top:1px dashed var(--line);margin-top:4px}
.static-row b{display:block;font-size:13px;color:var(--ink)}
.static-row small{color:var(--muted);font-size:12px}
@media (max-width:760px){.engine-wrap{grid-template-columns:1fr}}
</style>

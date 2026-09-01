import { defineStore } from "pinia";
import { ref } from "vue";
import * as api from "../api/client";

export const useSettingsStore = defineStore("settings", () => {
  const settings = ref<api.SettingsView | null>(null);
  async function load() {
    settings.value = await api.getSettings();
  }
  async function save(s: api.SettingsView) {
    settings.value = await api.saveSettings(s);
  }
  return { settings, load, save };
});

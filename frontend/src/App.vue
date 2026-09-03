<script setup lang="ts">
import { onMounted } from "vue";
import { useJobsStore } from "./stores/jobs";
import AppSidebar from "./components/AppSidebar.vue";
import AppTopbar from "./components/AppTopbar.vue";
import ToastHost from "./components/ToastHost.vue";

const jobs = useJobsStore();
onMounted(() => jobs.startPolling());
</script>

<template>
  <div class="workbench">
    <AppSidebar />
    <div class="work-main">
      <AppTopbar />
      <main class="work-content">
        <router-view v-slot="{ Component }">
          <Transition name="page" mode="out-in">
            <KeepAlive include="SettingsView">
              <component :is="Component" />
            </KeepAlive>
          </Transition>
        </router-view>
      </main>
    </div>
    <ToastHost />
  </div>
</template>

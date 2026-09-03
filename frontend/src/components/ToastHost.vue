<script setup lang="ts">
import { useToastStore } from "../stores/toast";
const toast = useToastStore();
</script>

<template>
  <Teleport to="body">
    <div class="toast-host">
      <TransitionGroup name="toast">
        <div v-for="t in toast.items" :key="t.id" class="toast" :class="t.ok ? 'ok' : 'bad'">
          <span>{{ t.ok ? "✓" : "✕" }}</span>{{ t.text }}
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style>
.toast-host{position:fixed;bottom:26px;left:50%;transform:translateX(-50%);z-index:999;display:flex;flex-direction:column;gap:8px;align-items:center;pointer-events:none}
.toast{background:#10261E;color:#E7FFF4;padding:10px 18px;border-radius:12px;box-shadow:0 16px 40px rgba(4,120,87,.25);font-size:13px;display:flex;gap:9px;align-items:center}
.toast.ok{border:1px solid var(--green-500)}
.toast.bad{border:1px solid #f87171}
.toast-enter-active,.toast-leave-active{transition:all .3s var(--ease)}
.toast-enter-from{opacity:0;transform:translateY(16px) scale(.96)}
.toast-leave-to{opacity:0;transform:translateY(8px)}
</style>

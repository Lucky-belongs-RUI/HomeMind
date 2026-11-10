<template>
  <router-view />
  <ToastContainer />
  <FloatingAvatar />
</template>

<script setup>
import ToastContainer from '@/components/common/ToastContainer.vue'
import FloatingAvatar from '@/components/agent/FloatingAvatar.vue'
</script>
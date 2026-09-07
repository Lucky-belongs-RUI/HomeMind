<template>
  <div class="w-full h-full flex items-center justify-center bg-gradient-to-br from-gray-50 to-white">
    <svg viewBox="0 0 120 80" fill="none" class="w-full h-full" preserveAspectRatio="xMidYMid meet">
      <!-- 空调 -->
      <template v-if="type === 'air_conditioner'">
        <rect x="10" y="15" width="100" height="50" rx="6" :fill="isOn ? '#f0f0f0' : '#e8e8e8'" stroke="#ccc" stroke-width="1.5" />
        <rect x="25" y="28" width="70" height="4" rx="2" :fill="isOn ? '#d4e8ff' : '#ddd'" />
        <rect x="25" y="36" width="70" height="4" rx="2" :fill="isOn ? '#c0e0ff' : '#ddd'" />
        <rect x="25" y="44" width="70" height="4" rx="2" :fill="isOn ? '#d4e8ff' : '#ddd'" />
        <rect x="72" y="18" width="28" height="8" rx="2" :fill="isOn ? '#1a1a2e' : '#333'" />
        <text v-if="isOn" x="80" y="24.5" font-size="6" fill="#00ff88" font-family="monospace">26°C</text>
        <circle v-if="isOn" cx="86" cy="46" r="3" fill="#4ade80" opacity="0.8" />
      </template>

      <!-- 灯 -->
      <template v-else-if="type === 'light'">
        <rect x="52" y="8" width="16" height="8" rx="2" fill="#888" />
        <rect x="57" y="16" width="6" height="12" fill="#999" />
        <path d="M35 32h50l-8 28H43l-8-28z" :fill="isOn ? '#fff8e1' : '#e8e8e8'" stroke="#ccc" stroke-width="1" />
        <template v-if="isOn">
          <ellipse cx="60" cy="46" rx="16" ry="10" fill="#ffd54f" opacity="0.3" />
          <ellipse cx="60" cy="46" rx="10" ry="6" fill="#ffeb3b" opacity="0.2" />
          <circle cx="60" cy="46" r="4" fill="#fff9c4" opacity="0.6" />
        </template>
        <circle v-else cx="60" cy="46" r="4" fill="#ccc" />
      </template>

      <!-- 窗帘 -->
      <template v-else-if="type === 'curtain'">
        <rect x="5" y="8" width="110" height="4" rx="2" fill="#888" />
        <circle cx="10" cy="10" r="5" fill="#777" />
        <circle cx="110" cy="10" r="5" fill="#777" />
        <path d="M10 12v58q10-4 20 0v-58z" :fill="isOn ? '#d4c5a9' : '#b8a88a'" opacity="0.85" />
        <path d="M10 12v58q5-2 10 0v-58z" :fill="isOn ? '#e0d2b8' : '#c8b898'" opacity="0.5" />
        <path d="M110 12v58q-10-4-20 0v-58z" :fill="isOn ? '#d4c5a9' : '#b8a88a'" opacity="0.85" />
        <path d="M110 12v58q-5-2-10 0v-58z" :fill="isOn ? '#e0d2b8' : '#c8b898'" opacity="0.5" />
        <line x1="58" y1="12" x2="58" y2="70" stroke="#aaa" stroke-width="0.5" stroke-dasharray="2 2" />
        <line x1="58" y1="70" x2="58" y2="78" stroke="#888" stroke-width="1" />
        <circle cx="58" cy="78" r="2" fill="#666" />
        <rect v-if="isOn" x="48" y="30" width="24" height="15" rx="2" fill="#fff9c4" opacity="0.2" />
      </template>

      <!-- 扫地机器人 -->
      <template v-else-if="type === 'robot_vacuum'">
        <ellipse cx="60" cy="48" rx="36" ry="22" :fill="isOn ? '#3a3a4a' : '#333'" />
        <ellipse cx="60" cy="48" rx="36" ry="22" stroke="#555" stroke-width="1" />
        <circle cx="60" cy="44" r="14" :fill="isOn ? '#2a2a3a' : '#282828'" />
        <circle cx="60" cy="44" r="6" :fill="isOn ? '#4488ff' : '#444'" />
        <circle cx="60" cy="44" r="2.5" :fill="isOn ? '#66aaff' : '#666'" />
        <rect x="48" y="62" width="10" height="5" rx="2" fill="#666" />
        <rect x="62" y="62" width="10" height="5" rx="2" fill="#666" />
        <circle v-if="isOn" cx="86" cy="36" r="2.5" fill="#4ade80" />
      </template>

      <!-- 音箱/智能马桶 -->
      <template v-else-if="type === 'speaker'">
        <rect x="38" y="10" width="44" height="60" rx="22" :fill="isOn ? '#3a3a4a' : '#333'" />
        <rect x="38" y="10" width="44" height="60" rx="22" stroke="#555" stroke-width="1" />
        <circle cx="60" cy="30" r="14" :fill="isOn ? '#2a2a3a' : '#282828'" />
        <circle cx="60" cy="30" r="14" :stroke="isOn ? '#6a6a8a' : '#444'" stroke-width="0.5" stroke-dasharray="2 2" />
        <circle cx="60" cy="30" r="6" :fill="isOn ? '#4a4a6a' : '#333'" />
        <circle v-if="isOn" cx="60" cy="30" r="3" fill="#93c5fd" opacity="0.6" />
        <ellipse cx="60" cy="54" rx="10" ry="5" :fill="isOn ? '#2a2a3a' : '#282828'" />
        <circle cx="60" cy="20" r="2" :fill="isOn ? '#93c5fd' : '#555'" />
      </template>

      <!-- 电视 -->
      <template v-else-if="type === 'tv'">
        <rect x="10" y="10" width="100" height="56" rx="4" :fill="isOn ? '#f0f0f0' : '#e2e2e2'" stroke="#ccc" stroke-width="1.5" />
        <rect x="16" y="16" width="88" height="44" rx="2" :fill="isOn ? '#1b2b4b' : '#333'" />
        <polygon v-if="isOn" points="42,34 72,38 42,44" fill="#7dd3fc" opacity="0.9" />
        <rect x="52" y="70" width="16" height="6" rx="2" fill="#888" />
        <rect x="42" y="66" width="36" height="4" rx="2" fill="#999" />
        <circle v-if="isOn" cx="95" cy="18" r="2.5" fill="#4ade80" />
      </template>

      <!-- 空气净化器 -->
      <template v-else-if="type === 'air_purifier'">
        <rect x="38" y="14" width="44" height="52" rx="10" :fill="isOn ? '#eef5ff' : '#e8e8e8'" stroke="#b9c8dc" stroke-width="1.5" />
        <rect x="44" y="20" width="32" height="18" rx="3" :fill="isOn ? '#dbeafe' : '#ddd'" />
        <rect x="44" y="24" width="32" height="3" rx="1.5" :fill="isOn ? '#60a5fa' : '#bbb'" />
        <rect x="44" y="30" width="32" height="3" rx="1.5" :fill="isOn ? '#93c5fd' : '#bbb'" />
        <rect x="44" y="36" width="32" height="3" rx="1.5" :fill="isOn ? '#bfdbfe' : '#bbb'" />
        <circle cx="60" cy="52" r="7" :fill="isOn ? '#3b82f6' : '#ccc'" opacity="0.7" />
        <circle cx="60" cy="52" r="3" :fill="isOn ? '#fff' : '#aaa'" />
      </template>

      <!-- 加湿器 -->
      <template v-else-if="type === 'humidifier'">
        <rect x="40" y="16" width="40" height="46" rx="10" :fill="isOn ? '#ecfeff' : '#e8e8e8'" stroke="#a5d8e0" stroke-width="1.5" />
        <rect x="46" y="22" width="28" height="14" rx="3" :fill="isOn ? '#cffafe' : '#ddd'" />
        <path d="M46 42q7-3 14 0t14 0" :stroke="isOn ? '#38bdf8' : '#ccc'" stroke-width="2" fill="none" stroke-linecap="round" />
        <circle cx="52" cy="52" r="2" :fill="isOn ? '#38bdf8' : '#bbb'" />
        <circle cx="60" cy="54" r="2" :fill="isOn ? '#38bdf8' : '#bbb'" />
        <circle cx="68" cy="52" r="2" :fill="isOn ? '#38bdf8' : '#bbb'" />
      </template>

      <!-- 热水器 -->
      <template v-else-if="type === 'water_heater'">
        <rect x="42" y="12" width="36" height="56" rx="12" :fill="isOn ? '#fff7ed' : '#e8e8e8'" stroke="#e5b98c" stroke-width="1.5" />
        <rect x="48" y="18" width="24" height="22" rx="4" :fill="isOn ? '#fed7aa' : '#ddd'" />
        <text v-if="isOn" x="60" y="32" text-anchor="middle" font-size="9" fill="#c2410c" font-family="monospace">45°C</text>
        <rect x="52" y="46" width="16" height="10" rx="2" :fill="isOn ? '#fdba74' : '#ccc'" opacity="0.8" />
        <circle cx="60" cy="66" r="2.5" :fill="isOn ? '#f97316' : '#bbb'" />
      </template>

      <!-- 洗衣机 -->
      <template v-else-if="type === 'washer'">
        <rect x="32" y="10" width="56" height="60" rx="6" :fill="isOn ? '#f0f9ff' : '#e8e8e8'" stroke="#b9c8dc" stroke-width="1.5" />
        <circle cx="60" cy="32" r="16" :fill="isOn ? '#dbeafe' : '#ddd'" stroke="#93c5fd" stroke-width="1" />
        <circle cx="60" cy="32" r="8" :fill="isOn ? '#bfdbfe' : '#ccc'" />
        <circle v-if="isOn" cx="60" cy="32" r="3" fill="#3b82f6" opacity="0.6" />
        <rect x="42" y="58" width="36" height="3" rx="1.5" :fill="isOn ? '#93c5fd' : '#ccc'" />
        <circle v-if="isOn" cx="90" cy="18" r="2.5" fill="#4ade80" />
      </template>

      <!-- 冰箱 -->
      <template v-else-if="type === 'fridge'">
        <rect x="30" y="8" width="60" height="64" rx="6" :fill="isOn ? '#eff6ff' : '#e8e8e8'" stroke="#bfdbfe" stroke-width="1.5" />
        <rect x="36" y="14" width="24" height="26" rx="2" :fill="isOn ? '#dbeafe' : '#ddd'" />
        <rect x="62" y="14" width="24" height="26" rx="2" :fill="isOn ? '#e0e7ff' : '#ddd'" />
        <line x1="36" y1="44" x2="84" y2="44" stroke="#93c5fd" stroke-width="1.5" />
        <rect x="44" y="50" width="32" height="16" rx="2" :fill="isOn ? '#dbeafe' : '#ddd'" opacity="0.8" />
        <line x1="50" y1="56" x2="70" y2="56" stroke="#60a5fa" stroke-width="1.5" />
      </template>

      <!-- 智能门锁 -->
      <template v-else-if="type === 'door_lock'">
        <rect x="38" y="18" width="44" height="44" rx="6" :fill="isOn ? '#fefce8' : '#e8e8e8'" stroke="#d9c56f" stroke-width="1.5" />
        <rect x="50" y="8" width="20" height="14" rx="4" :fill="isOn ? '#fde68a' : '#ccc'" stroke="#d9c56f" stroke-width="1" />
        <circle cx="60" cy="40" r="7" :fill="isOn ? (locked ? '#f59e0b' : '#34d399') : '#aaa'" />
        <rect x="58" y="42" width="4" height="10" rx="2" :fill="isOn ? '#92400e' : '#888'" />
        <rect x="64" y="44" width="8" height="4" rx="1" :fill="isOn ? (locked ? '#f59e0b' : '#34d399') : '#aaa'" />
      </template>

      <!-- 摄像头 -->
      <template v-else-if="type === 'camera'">
        <rect x="28" y="22" width="64" height="26" rx="6" :fill="isOn ? '#f0f0f5' : '#e2e2e2'" stroke="#b0b0c4" stroke-width="1.5" />
        <circle cx="60" cy="35" r="9" :fill="isOn ? '#2b2b3a' : '#444'" />
        <circle cx="60" cy="35" r="4" :fill="isOn ? (recording ? '#ef4444' : '#60a5fa') : '#666'" />
        <rect x="92" y="28" width="8" height="14" rx="2" :fill="isOn ? '#3a3a4a' : '#555'" />
        <rect x="54" y="48" width="12" height="14" rx="2" :fill="isOn ? '#3a3a4a' : '#555'" />
        <circle v-if="isOn && recording" cx="32" cy="28" r="2.5" fill="#ef4444" />
      </template>
      <!-- 空气质量检测仪 -->
      <template v-else-if="type === 'air_monitor'">
        <rect x="26" y="12" width="68" height="56" rx="8" :fill="isOn ? '#f0f9ff' : '#e8e8e8'" stroke="#a8cfe8" stroke-width="1.5" />
        <rect x="34" y="20" width="52" height="20" rx="3" :fill="isOn ? '#1b2b3b' : '#333'" />
        <text x="40" y="34" font-size="8" fill="#7dd3fc" font-family="monospace">PM2.5</text>
        <rect x="34" y="46" width="52" height="12" rx="3" :fill="isOn ? '#dbeafe' : '#ddd'" />
        <line x1="38" y1="52" x2="82" y2="52" stroke="#60a5fa" stroke-width="2" stroke-linecap="round" :opacity="isOn ? 0.8 : 0.3" />
        <circle v-if="isOn" cx="90" cy="18" r="2.5" fill="#4ade80" />
      </template>

      <!-- 温湿度传感器 / 室外温湿度传感器 -->
      <template v-else-if="type === 'temp_humidity_sensor' || type === 'outdoor_sensor'">
        <circle cx="60" cy="42" r="24" :fill="isOn ? '#f0f9ff' : '#e8e8e8'" stroke="#a8cfe8" stroke-width="1.5" />
        <rect x="52" y="10" width="16" height="8" rx="2" fill="#8899aa" />
        <path d="M56 24q-5 6-5 11a9 9 0 0 0 18 0q0-5-5-11z" :fill="isOn ? '#fb7185' : '#cbd5e1'" opacity="0.85" />
        <circle cx="60" cy="35" r="2" :fill="isOn ? '#be123c' : '#94a3b8'" />
        <path d="M48 55q4 5 12 5t12-5" :stroke="isOn ? '#38bdf8' : '#b6c6d4'" stroke-width="2" stroke-linecap="round" fill="none" />
        <path v-if="type === 'outdoor_sensor'" d="M28 22q-3-8 4-10M78 20q4-6 10-4M88 30q6 0 5 7" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" fill="none" />
      </template>

      <!-- 室外气象站 -->
      <template v-else-if="type === 'weather_station'">
        <rect x="52" y="10" width="16" height="18" rx="3" :fill="isOn ? '#eef5ff' : '#e2e2e2'" stroke="#9fc3e8" stroke-width="1.2" />
        <path d="M48 30l24 12-6 6-12-6z" :fill="isOn ? '#60a5fa' : '#b6c6d4'" />
        <circle cx="46" cy="22" r="7" :fill="isOn ? '#fde68a' : '#e5d9b8'" />
        <path d="M58 26a10 10 0 0 1 10 10" :stroke="isOn ? '#93c5fd' : '#cbd5e1'" stroke-width="2" fill="none" stroke-linecap="round" />
        <rect x="52" y="44" width="16" height="24" rx="4" :fill="isOn ? '#f0f9ff' : '#e8e8e8'" stroke="#a8cfe8" stroke-width="1.2" />
        <line x1="57" y1="52" x2="63" y2="52" :stroke="isOn ? '#38bdf8' : '#b6c6d4'" stroke-width="2" stroke-linecap="round" />
        <line x1="57" y1="58" x2="63" y2="58" :stroke="isOn ? '#38bdf8' : '#b6c6d4'" stroke-width="2" stroke-linecap="round" />
      </template>

      <!-- 智能电表 -->
      <template v-else-if="type === 'electricity_meter'">
        <rect x="28" y="14" width="64" height="52" rx="6" :fill="isOn ? '#fefce8' : '#e8e8e8'" stroke="#e0c56a" stroke-width="1.5" />
        <rect x="36" y="22" width="48" height="24" rx="3" :fill="isOn ? '#1b2b3b' : '#333'" />
        <text v-if="isOn" x="42" y="38" font-size="8" fill="#fde047" font-family="monospace">186.5 kWh</text>
        <circle cx="38" cy="58" r="2" :fill="isOn ? '#4ade80' : '#ccc'" />
        <line x1="46" y1="58" x2="82" y2="58" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" :opacity="isOn ? 0.8 : 0.3" />
        <path d="M82 46q6 0 6-6t-6-6" :stroke="isOn ? '#f59e0b' : '#ddd'" stroke-width="2" fill="none" />
      </template>

      <!-- 智能插座 -->
      <template v-else-if="type === 'smart_plug'">
        <rect x="36" y="18" width="48" height="44" rx="6" :fill="isOn ? '#f5f5f5' : '#e8e8e8'" stroke="#b6b6c8" stroke-width="1.5" />
        <rect x="46" y="26" width="28" height="18" rx="2" :fill="isOn ? '#2b2b3a' : '#555'" />
        <rect x="52" y="30" width="5" height="10" rx="1" fill="#fff" opacity="0.9" />
        <rect x="63" y="30" width="5" height="10" rx="1" fill="#fff" opacity="0.9" />
        <rect x="54" y="48" width="12" height="5" rx="2" :fill="isOn ? '#10b981' : '#a1a1aa'" />
        <path d="M74 36q5 0 5-4" :stroke="isOn ? '#f59e0b' : '#ddd'" stroke-width="2" fill="none" stroke-linecap="round" />
      </template>

      <!-- 智能水表 -->
      <template v-else-if="type === 'water_meter'">
        <rect x="26" y="14" width="68" height="52" rx="8" :fill="isOn ? '#f0f9ff' : '#e8e8e8'" stroke="#a8cfe8" stroke-width="1.5" />
        <circle cx="60" cy="38" r="17" :fill="isOn ? '#e0f2fe' : '#eee'" stroke="#7dd3fc" stroke-width="1.5" />
        <path d="M60 27v10l6 4" :stroke="isOn ? '#0284c7' : '#94a3b8'" stroke-width="2.5" stroke-linecap="round" fill="none" />
        <circle cx="60" cy="38" r="2" :fill="isOn ? '#0284c7' : '#94a3b8'" />
        <path d="M44 60q4-6 8-6t8 6" :stroke="isOn ? '#38bdf8' : '#b6c6d4'" stroke-width="1.5" fill="none" stroke-linecap="round" />
      </template>

      <!-- 智能燃气表 -->
      <template v-else-if="type === 'gas_meter'">
        <rect x="28" y="16" width="64" height="48" rx="7" :fill="isOn ? '#fff7ed' : '#e8e8e8'" stroke="#e5b98c" stroke-width="1.5" />
        <rect x="36" y="24" width="48" height="20" rx="3" :fill="isOn ? '#1b2b3b' : '#333'" />
        <text v-if="isOn" x="42" y="38" font-size="8" fill="#fdba74" font-family="monospace">12.8 m³</text>
        <path d="M54 52q-3-4 0-7t0-7q3 4 0 7t0 7z" :fill="isOn ? '#f97316' : '#cbd5e1'" />
      </template>

      <!-- 门窗传感器 -->
      <template v-else-if="type === 'door_window_sensor'">
        <rect x="20" y="26" width="34" height="20" rx="5" :fill="isOn ? '#f0f9ff' : '#e8e8e8'" stroke="#a8cfe8" stroke-width="1.5" />
        <rect x="26" y="32" width="8" height="8" rx="2" :fill="isOn ? '#38bdf8' : '#cbd5e1'" />
        <rect x="66" y="26" width="34" height="20" rx="5" :fill="isOn ? '#f0f9ff' : '#e8e8e8'" stroke="#a8cfe8" stroke-width="1.5" />
        <rect x="86" y="32" width="8" height="8" rx="2" :fill="isOn ? '#38bdf8' : '#cbd5e1'" />
        <path d="M54 36h12" :stroke="isOn ? '#10b981' : '#cbd5e1'" stroke-width="2.5" stroke-dasharray="3 3" />
        <circle cx="54" cy="36" r="3" :fill="isOn ? '#34d399' : '#cbd5e1'" />
      </template>

      <!-- 人体存在传感器 -->
      <template v-else-if="type === 'presence_sensor'">
        <rect x="40" y="34" width="40" height="10" rx="5" :fill="isOn ? '#eef2ff' : '#e8e8e8'" stroke="#a5b4fc" stroke-width="1.5" />
        <path d="M52 28a13 13 0 0 1 16 0" :stroke="isOn ? '#6366f1' : '#cbd5e1'" stroke-width="2.5" stroke-linecap="round" fill="none" />
        <path d="M56 20a9 9 0 0 1 8 0" :stroke="isOn ? '#818cf8' : '#d5dbe8'" stroke-width="2" stroke-linecap="round" fill="none" />
        <path d="M56 48q4 5 8 0" :stroke="isOn ? '#6366f1' : '#cbd5e1'" stroke-width="2" stroke-linecap="round" fill="none" />
        <circle cx="60" cy="42" r="5" :fill="isOn ? '#818cf8' : '#cbd5e1'" opacity="0.85" />
      </template>

      <!-- 水浸传感器 -->
      <template v-else-if="type === 'leak_sensor'">
        <rect x="34" y="24" width="52" height="30" rx="6" :fill="isOn ? '#f0f9ff' : '#e8e8e8'" stroke="#a8cfe8" stroke-width="1.5" />
        <path d="M60 16q-7 8-7 13a7 7 0 0 0 14 0q0-5-7-13z" :fill="isOn ? '#38bdf8' : '#cbd5e1'" />
        <path d="M44 40h32" :stroke="isOn ? '#0284c7' : '#94a3b8'" stroke-width="3" stroke-linecap="round" />
        <path d="M46 48h28" :stroke="isOn ? '#7dd3fc' : '#cbd5e1'" stroke-width="2" stroke-linecap="round" />
        <path d="M74 20v-4M78 24h4" :stroke="isOn ? '#ef4444' : '#ddd'" stroke-width="2" stroke-linecap="round" />
      </template>

      <!-- 燃气传感器 -->
      <template v-else-if="type === 'gas_sensor'">
        <circle cx="60" cy="42" r="22" :fill="isOn ? '#fff7ed' : '#e8e8e8'" stroke="#e5b98c" stroke-width="1.5" />
        <path d="M60 26q-8 10-8 15a8 8 0 0 0 16 0q0-5-8-15z" :fill="isOn ? '#fb923c' : '#cbd5e1'" />
        <path d="M60 36v6l4 3" :stroke="isOn ? '#7c2d12' : '#94a3b8'" stroke-width="2" stroke-linecap="round" fill="none" />
        <rect x="52" y="56" width="16" height="6" rx="2" :fill="isOn ? '#f97316' : '#cbd5e1'" />
      </template>

      <!-- 烟雾传感器 -->
      <template v-else-if="type === 'smoke_sensor'">
        <path d="M60 8q14 6 14 18a12 12 0 0 1-4 22H50a12 12 0 0 1-4-22q0-12 14-18z" :fill="isOn ? '#fef3c7' : '#e8e8e8'" stroke="#e3c15a" stroke-width="1.5" />
        <path d="M52 34q3-5 8-3M58 40q3-5 8-3" :stroke="isOn ? '#94a3b8' : '#cbd5e1'" stroke-width="2" stroke-linecap="round" fill="none" />
        <circle cx="60" cy="50" r="7" :fill="isOn ? '#fbbf24' : '#e5d9b8'" />
        <rect x="52" y="62" width="16" height="8" rx="3" :fill="isOn ? '#94a3b8' : '#cbd5e1'" />
      </template>

      <!-- 智能路由器 -->
      <template v-else-if="type === 'router'">
        <rect x="30" y="38" width="60" height="26" rx="7" :fill="isOn ? '#f5f5f5' : '#e8e8e8'" stroke="#b6b6c8" stroke-width="1.5" />
        <rect x="38" y="44" width="26" height="14" rx="3" :fill="isOn ? '#1b2b3b' : '#333'" />
        <circle cx="80" cy="50" r="2.5" :fill="isOn ? '#10b981' : '#cbd5e1'" />
        <circle cx="88" cy="50" r="2.5" :fill="isOn ? '#f59e0b' : '#cbd5e1'" />
        <path d="M58 10l6 12h-12z" :fill="isOn ? '#6366f1' : '#b6c6d4'" />
        <path d="M84 18q6-6 10-14" :stroke="isOn ? '#818cf8' : '#cbd5e1'" stroke-width="2.5" stroke-linecap="round" fill="none" />
        <path d="M84 24q10-8 14-18" :stroke="isOn ? '#a5b4fc' : '#d5dbe8'" stroke-width="2" stroke-linecap="round" fill="none" />
      </template>

      <!-- 通用设备 -->
      <template v-else>
        <rect x="25" y="15" width="70" height="50" rx="8" :fill="isOn ? '#e8e8f0' : '#e0e0e0'" stroke="#ccc" stroke-width="1.5" />
        <rect x="45" y="25" width="30" height="20" rx="3" :fill="isOn ? '#4488ff' : '#aaa'" :opacity="isOn ? 0.6 : 0.4" />
        <circle cx="60" cy="35" r="6" :fill="isOn ? '#66aaff' : '#bbb'" :opacity="isOn ? 0.8 : 0.5" />
        <circle cx="45" cy="55" r="2" :fill="isOn ? '#4ade80' : '#ccc'" />
        <circle cx="52" cy="55" r="2" :fill="isOn ? '#60a5fa' : '#ccc'" />
        <circle cx="59" cy="55" r="2" :fill="isOn ? '#f59e0b' : '#ccc'" />
      </template>
    </svg>
  </div>
</template>

<script setup>
defineProps({
  type: { type: String, default: 'default' },
  isOn: { type: Boolean, default: false },
  locked: { type: Boolean, default: false },
  recording: { type: Boolean, default: false },
})
</script>
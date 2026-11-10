# 智能家居大模型体验平台 - 前端

基于 Vue 3 + Vite 5 + Pinia + Vue Router + Element Plus 的 SPA 前端，实现开发文档第 5 章的全部页面，界面风格参考 AI-3/frontend 的玻璃拟态设计（蓝色主色 `#3b82f6`）。

页面清单：

- 登录 / 注册：JWT 认证，注册新家庭后自动成为房主
- 设备管理（DeviceView）：设备图像卡片、展开式控制、筛选、添加/编辑/删除
- 房间管理（RoomView）：房间侧边栏、房间详情、设备卡片
- AI 助理（AgentView）：虚拟形象、文字/语音交互、快捷指令、文件上传，全部 AI 功能集中在此页
- 家庭管理（UserView）：家庭概览、成员列表、房主创建子账户、偏好画像、权限说明
- 数据上传（FileUploadView）：PDF/Word 上传、知识库文件状态轮询

## 运行方法

环境要求：Node.js 18+，npm 9+。

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 http://localhost:5173。

## 演示账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 房主 | owner01 | 123456 |
| 住户 | resident01 | 123456 |
| 访客 | guest01 | 123456 |

演示账号可直接登录，也可前往 `/register` 注册新家庭（登录页不提供快捷填充）。

## 开发预览与后端对接

- 前端已移除 mock 演示层，所有请求（含 WebSocket）始终连接真实后端。
- 无需任何 mock 开关：确保 FastAPI 后端运行在 `http://localhost:8000`，Vite 已配置 `/api` 代理（含 WebSocket），也可通过 `VITE_WS_URL` 指定 WebSocket 地址。
- 设备状态以 MySQL/后端为唯一数据源，前端本地不保存业务状态。

## 核心说明

- 主布局按开发文档 5.3 设计：顶部导航栏包含品牌、横向菜单（设备 / 房间 / AI 助理 / 家庭管理 / 数据上传）、家庭名、角色标签、昵称与退出登录。
- 所有请求由 `src/api/request.js` 统一注入 `Authorization: Bearer <token>`，后端从 JWT 解析 `user_id / role / family_id`，实现家庭隔离与角色权限；401 自动跳转登录页。
- WebSocket 由 `src/composables/useWebSocket.js` 全局单例管理，`device_status_update` 按当前家庭过滤。
- 权限遵循开发文档 5.15 权限矩阵，`src/composables/usePermission.js` 集中定义：房主可管理全部数据，住户可控制设备，访客仅可查看。
- 虚拟形象使用 Lottie 动画（`src/assets/lottie/`），支持 idle / speaking / thinking / sad 状态。
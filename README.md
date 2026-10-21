# Art_assessment

艺术素质测评系统前端，覆盖学生端、教师端、学校/区县/市州/省级管理端和题库管理端。

## 技术栈

- Vue 3、TypeScript、Vite
- Pinia、Vue Router
- Element Plus、ECharts
- Axios、Day.js

## 本地运行

```powershell
pnpm install
pnpm dev
```

默认使用 `Mock` 数据，登录页可以直接选择学生、学校、区县、市州、省级或题库管理员角色。

生产构建：

```powershell
pnpm typecheck
pnpm build
pnpm preview
```

## 接入真实后端

复制 `.env.example` 为 `.env.local`，并设置：

```text
VITE_API_BASE_URL=/api/v1
VITE_USE_MOCK=false
```

接口契约以项目根目录的 `api11.md` 为准。前端请求统一经过 `src/api/client.ts`，页面不直接创建 Axios 实例。

## 目录

```text
src/
  api/          统一请求、Mock 数据和业务服务
  components/   状态、页头、指标卡等通用组件
  config/       角色菜单和业务配置
  layouts/      管理端应用壳
  router/       权限路由
  stores/       登录态与用户权限
  styles/       全局设计令牌和响应式样式
  types/        业务类型
  views/        管理工作台、题库端和学生端页面
```

前端 A/B 的统一协作约定见 `FRONTEND_CONVENTIONS.md`。

前端 A 功能覆盖见 `FRONTEND_A_COVERAGE.md`，前端 B 功能覆盖见 `TASK_COVERAGE.md`。

前端 A 已补齐学生端和教师端完整页面入口、表单、答题资源、逐题解析、人工评分、学习报告、证书、作品和个人资料。

新版功能设计表按端统计为：学生端 54 项、教师端 51 项、学校端 31 项、区县端 26 项、市州端 33 项、省级管理员端 46 项、题库管理端 27 项，共 268 项。

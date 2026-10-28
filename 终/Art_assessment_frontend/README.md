# 艺术素质测评系统 — 前端

> 项目更改记录见 [../CHANGELOG.md](../CHANGELOG.md)。

从 `Art_assessment` 全栈项目中拆分出来的独立前端工程。

## 技术栈

- Vue 3 + TypeScript
- Vite 7
- Element Plus（中文语言包）
- Pinia
- Vue Router
- ECharts
- Axios

## 快速开始

```bash
# 安装依赖（需要 Node.js 20+ / pnpm）
pnpm install

# 开发模式（http://localhost:5173）
pnpm dev

# 类型检查 + 构建
pnpm build

# 预览构建产物
pnpm preview
```

## 环境变量

**默认不需要 `.env`**：未设置 `VITE_USE_MOCK` 时直接调用真实后端，
接口前缀默认 `/api/v1`，代理到 `http://localhost:8000`。

需要覆盖时复制 `.env.example` 为 `.env`（或 `.env.local`）后修改：

| 变量 | 说明 |
| --- | --- |
| `VITE_API_BASE_URL` | 接口前缀，默认 `/api/v1` |
| `VITE_USE_MOCK` | `true` 使用内置 mock；不设置或 `false` 调用真实后端（默认） |
| `VITE_APP_TITLE` | 页面标题 |

### 与后端联调

1. 先启动后端（默认 `http://localhost:8000`）。
2. 直接运行 `pnpm dev`（或 `npm run dev`）即可，无需创建 `.env`。
3. Vite 已配置代理：`/api` 和 `/media` → `http://localhost:8000`（见 `vite.config.ts`）。
4. 只想看界面、不启动后端时，再设置 `VITE_USE_MOCK=true`（修改后需重启 Vite）。

后端演示账号密码：`Demo@123456`。

### 作答与作品上传

学生测评页支持单选、多选、判断、填空、简答和图片/音频作品上传：

- 图片题限 JPG/PNG/WEBP，音频题限 MP3/WAV/M4A/WEBM/OGG，单个文件不超过 20 MB；
- 音乐实践题（音频作品题）支持「直接录音」：调用浏览器麦克风录制，最长 5 分钟，
  停止后自动转为 24 kHz 单声道 WAV 并上传；不支持录音或转码失败时回退上传原始录音文件；
- 录音过程中可随时取消，切换题目、交卷或保存并退出会自动取消未完成的录音；
- 上传成功后立即写入该题答案，预览通过 `/media/` 代理加载；
- 答题页每 15 秒自动保存，也可手动「保存答案」；
- 「保存并退出」后考试继续计时，测评卡片会显示「继续作答」和剩余时间；
- 学生随机练习固定 10 题（6 单选 + 3 多选 + 1 实践题），不含需要人工评分的简答题；
- 含简答题的测评交卷后不立即出成绩，页面提示「等待教师评分」并返回测评列表；
  教师在评分页完成终评后，学生才能在「我的成绩」看到分数与解析；
- 评分页和成绩页会把上传作品显示为图片预览或音频播放器；
- 教师「题库查询」和题库端「试题管理」支持全部 8 种题型筛选，
  每页可选 10 / 20 / 50 / 100 条。

### 审核入口

- 试题审核：只在题库管理端 `/qbank/questions`。
- 试卷审核：只在题库管理端 `/paper-review`，菜单位于「题库管理」分组。
- 教师、学校、区县、市州、省管理员在组卷管理页只能「提交审核」和查看「审核记录」，
  不再显示通过 / 驳回按钮。

常用联调账号（按后端 `seed_demo` / `seed_demo_accounts` 生成）：

| 账号 | 角色 | 姓名 | 说明 |
| --- | --- | --- | --- |
| `school_admin` | 学校管理员 | 王建国 | 本校班级、账号与教学管理 |
| `teacher` / `teacher_music` / `teacher_art` | 教师 | 陈志远 / 李静 / 赵敏 | 班级、学生、题库、组卷、测评与评分；`teacher` 任教七年级（1）班 |
| `student` / `student_001` | 学生 | 王浩然 / 张子涵 | 七年级（1）班 |
| `student2` / `student_002` | 学生 | 李雨桐 / 刘思远 | 七年级（1）班 |
| `district_admin` / `city_admin` / `province_admin` / `question_admin` | 各级管理 | 刘敏 / 陈建平 / 周立新 / 孙倩 | 区域统计、题库与审核 |

登录页无需先选择工作端：直接输入账号和密码，系统按账号角色自动进入对应工作端。
表单下方提供 7 个测试账号按钮，点击即可填入该工作端的账号与密码（真实模式为 `Demo@123456`）。

> 当前数据库已执行 `realify_demo_data --purge-records` 清理：账号、班级、课程和
> 3600 道题库保留，学校为四川省成都市青羊区的九年一贯制学校
> 「成都市石室联合中学蜀华分校」，包含小学部（三年级、六年级）和初中部（七、八年级），
> 共 7 个班、124 名学生；试卷 / 测评 / 成绩 / 证书等演示记录已清空，
> 相关列表为空属于预期结果。

> 注意：mock 模式登录提示的密码与真实后端不同，联调时以真实后端的 `Demo@123456` 为准。

## 目录结构

```
src/
├── api/          # 请求封装、接口定义、mock 数据
├── assets/       # 静态资源（登录背景等）
├── components/   # 通用组件
├── config/       # 应用配置
├── layouts/      # 布局（AppShell 等）
├── router/       # 路由与角色守卫
├── stores/       # Pinia 状态
├── styles/       # 全局样式
├── types/        # TypeScript 类型
├── utils/        # 工具（ECharts 按需引入、角色路由）
└── views/        # 页面（含 student/ 学生端）
```

## 脚本

- `pnpm dev`：启动开发服务器（`--host 0.0.0.0`，局域网可访问）
- `pnpm build`：`vue-tsc` 类型检查后打包到 `dist/`
- `pnpm typecheck`：仅做类型检查
- `pnpm preview`：本地预览构建产物

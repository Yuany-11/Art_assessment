# 艺术素质测评系统

面向小学、初中音乐与美术学科的测评系统，包含 Django 后端与 Vue 3 前端两个工程。

| 目录 | 说明 | 技术栈 |
| --- | --- | --- |
| `Art_assessment_backend/` | 接口、题库、测评、评分、报表 | Python 3.11+ / Django 5.2 / DRF / SQLite |
| `Art_assessment_frontend/` | 学生端、教师端、各级管理端、题库端 | Vue 3 / TypeScript / Vite / Element Plus |
| `CHANGELOG.md` | 更改记录（含每次修改时间） | — |
| `docs/` | 检查报告、归档 | — |

> 本仓库**不包含**数据库文件（`db.sqlite3`）、上传文件（`media/`）和 `.env`。
> 这些会在自己电脑上首次运行时生成，按下面步骤操作即可。

---

## 一、环境要求

| 工具 | 版本要求 | 检查命令 |
| --- | --- | --- |
| Python | 3.11 及以上（推荐 3.12） | `python --version` |
| Node.js | 20.19+ 或 22.12+（Vite 7 要求） | `node --version` |
| npm | 随 Node 安装，或使用 pnpm | `npm --version` |

不需要 MySQL、Redis、MinIO：本地默认使用 SQLite + 进程内缓存 + 本地文件存储。

## 二、后端（先启动）

```bash
cd Art_assessment_backend

# 1. 创建虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 2. 安装依赖（本地版不含 mysqlclient，Windows 无需编译工具）
pip install -r requirements-local.txt

# 3. 一条命令完成建表 + 全部演示数据（首次运行约 2~5 分钟）
python manage.py bootstrap_demo

# 4. 启动后端
python manage.py runserver
```

后端地址：<http://127.0.0.1:8000>（接口前缀 `/api/v1`，OpenAPI 描述 `/api/schema/`，后台 `/admin/`）。

`bootstrap_demo` 依次执行 `migrate`、`seed_menus`、`seed_organizations`、
`seed_demo_accounts`、`seed_demo`、`seed_question_bank`、`seed_rich_demo`、
`seed_all_portals`、`seed_classes`、`seed_primary_classes`、`realify_demo_data`，
可重复执行（各步骤幂等）。顺序不能改：`seed_all_portals` 自动组卷需要上传类题目，
题库必须先就绪；最后一步把演示组织、账号与题目替换为真实的四川学校与姓名。
快速模式 `--skip-bank` 会跳过题库与全端口演示数据，初始化更快但页面数据较少。

> 不需要 `.env`。如需自定义配置，`cp .env.example .env` 后修改，
> `.env.example` 已按 SQLite + LocMem + 本地文件写好。

<details>
<summary>也可以按顺序手动执行各 seed 命令</summary>

```bash
python manage.py migrate
python manage.py seed_menus              # 角色菜单
python manage.py seed_organizations      # 省/市/区县/学校
python manage.py seed_demo_accounts      # 七类角色演示账号（密码 Demo@123456）
python manage.py seed_demo               # 课程、班级、试卷、测评、成绩
python manage.py seed_question_bank      # 音乐/美术共 3600 道题 + 章节知识讲解（要先于 seed_all_portals）
python manage.py seed_rich_demo          # 分类题库、自动组卷、学情报告、证书
python manage.py seed_all_portals        # 为全部学生/教师补齐各页面数据（自动组卷依赖题库）
python manage.py seed_classes            # 中学 4 个班，每班约 20 名学生
python manage.py seed_primary_classes    # 小学部 2 个班
python manage.py realify_demo_data       # 换成真实学校/姓名/题目（不删业务记录）
```

</details>

## 三、前端

```bash
cd Art_assessment_frontend

npm install        # 或 pnpm install
npm run dev        # http://localhost:5173
```

**不需要创建 `.env`**：未设置 `VITE_USE_MOCK` 时默认调用真实后端，
Vite 会把 `/api`、`/media` 代理到 `http://127.0.0.1:8000`。

只想看界面、不启动后端时，创建 `Art_assessment_frontend/.env.local`：

```text
VITE_USE_MOCK=true
```

## 四、演示账号

登录页可直接点角色按钮快速填入，密码统一为 `Demo@123456`。

| 角色 | 账号 | 姓名 |
| --- | --- | --- |
| 学生 | `student` | 王浩然 |
| 学生 | `student_001` | 张子涵 |
| 教师 | `teacher` | 陈志远（音乐） |
| 教师 | `teacher_music` | 李静 |
| 教师 | `teacher_art` | 赵敏 |
| 学校管理员 | `school_admin` | 王建国 |
| 区县管理员 | `district_admin` | 刘敏 |
| 市州管理员 | `city_admin` | 陈建平 |
| 省管理员 | `province_admin` | 周立新 |
| 题库管理员 | `question_admin` | 孙倩 |

登录时不再先选端口：输入账号后，系统按账号角色自动进入对应端。

## 五、打包发给组员时

把项目文件夹发给别人时，**不要带本机专属目录**，否则对方会用到你这台机器编译出来的文件：

| 应当包含 | 不要包含 |
| --- | --- |
| `Art_assessment_backend/`（源码、`requirements*.txt`、`.env.example`、`media/.gitkeep`） | `node_modules/`、`dist/` |
| `Art_assessment_frontend/`（源码、`package.json`、`pnpm-lock.yaml`、`.env.example`） | `.venv/`、`venv/`、`__pycache__/`、`.pytest_cache/` |
| `README.md`、`CHANGELOG.md` | `db.sqlite3`、`.env`、`media/` 里的上传文件 |
| `docs/`（可选，说明文档） | `_backup_20261027_before_cleanup/`（旧备份，含旧数据库） |

如果直接压缩整个文件夹，建议先删除上表右列的内容；对方拿到后按第二节、第三节重新安装依赖即可。
对方首次运行时数据库是空的，**必须执行一次 `python manage.py bootstrap_demo`**。

## 六、常见问题

**1. 页面显示的是假数据 / 各页面数据都一样**
旧版本前端在缺少 `.env` 时默认走 Mock。当前版本已改为**默认调用真实后端**，
拉取最新代码后无需配置。若仍想用 Mock，显式设置 `VITE_USE_MOCK=true`。

**2. 后端启动报 MySQL 连接失败（`Can't connect to MySQL server`）**
说明环境里存在 `DB_ENGINE=mysql`。当前 `config/settings/dev.py` 默认使用 SQLite；
删除或修改 `.env` 中的 `DB_ENGINE`，或改为 `DB_ENGINE=sqlite`。

**3. `pip install` 在 mysqlclient 处失败**
本地演示不需要 MySQL，改用 `pip install -r requirements-local.txt`。
只有连接 MySQL 时才需要 `requirements.txt`，且 Windows 需装 MySQL 客户端库或 Visual C++ Build Tools。

**4. 能登录但所有列表为空**
没有初始化数据。执行 `python manage.py bootstrap_demo`（可重复执行，不会重复插入）。

**5. 账号密码不对**
执行 `python manage.py seed_demo_accounts` 会把演示账号密码重置为 `Demo@123456`。

**6. 端口被占用**
后端换端口：`python manage.py runserver 8001`（需同步改 `vite.config.ts` 里的代理地址）；
前端换端口：`npm run dev -- --port 5174`。

**7. 上传图片/音频失败**
确认 `Art_assessment_backend/media/` 目录存在且可写（项目内置 `.gitkeep`，存在即可）。

**8. 前端 `npm run dev` 报 Node 版本过低**
Vite 7 需要 Node 20.19+ 或 22.12+，升级 Node 后重新 `npm install`。

**9. 提示 `python` 不是内部或外部命令**
安装 Python 时勾选 “Add Python to PATH”，或改用 `py -3` 执行本节命令。

---

## 七、其他常用命令

```bash
# 后端测试
python -m pytest -q

# 前端类型检查与构建
npm run typecheck
npm run build

# 单独补充趣味课堂章节知识讲解（幂等）
python manage.py seed_chapter_knowledge

# 后台定时任务（自动交卷、结束测评、发证、成绩导入）
python manage.py auto_submit_attempts
python manage.py finish_assessments
python manage.py generate_certificates
python manage.py process_score_imports
```

# 前端 A 功能覆盖

范围：学生端与学生、教师主责功能 F001-F105。前端页面与真实接口调用路径已完成，当前默认使用 Mock 进行完整演示。

| 功能编号 | 能力 | 实现位置 |
|---|---|---|
| F001-F008 | 班级号查询、信息查看、加入、退出、转班、操作提示 | `StudentHomeView.vue` |
| F005 | 趣味课堂知识与课程章节展示 | `StudentKnowledgeView.vue` |
| F009-F020 | 音乐/美术随机练习、试卷信息、试题、答案和解析 | `StudentAssessmentsView.vue`、`StudentAttemptView.vue`、`StudentResultsView.vue` |
| F021-F035 | 音乐/美术正式测评、资源查看、倒计时、自动保存和自动交卷 | `StudentAssessmentsView.vue`、`StudentAttemptView.vue` |
| F036 | 课外自主学习图片上传 | `StudentArtworkView.vue`、`StudentHomeView.vue` |
| F037-F041 | 测评记录、成绩、正确率、分析报告、成长曲线 | `StudentResultsView.vue`、`StudentReportView.vue` |
| F042-F045 | 音乐/美术证书查看和下载 | `StudentCertificatesView.vue` |
| F046-F054 | 班级号/名称检索测评、班级成绩、个人成长、个人信息查看修改 | `StudentAssessmentsView.vue`、`StudentResultsView.vue`、`StudentReportView.vue`、`ProfileView.vue` |
| F055-F061 | 教师班级搜索、创建、修改、解散、申请加入 | `ClassesView.vue` |
| F062 | 班级学生批量导入 | `ClassesView.vue` |
| F063-F066 | 学生入班、退出、转班及科任教师申请审核 | `ClassesView.vue` |
| F067-F073 | 学生查询、学籍查看、身份材料、密码重置和外校学生导入 | `TeacherStudentsView.vue` |
| F074-F078 | 按学科、难度、题型和年级查询题库 | `TeacherQuestionBankView.vue` |
| F079-F089 | 手动/自动组卷、暂存、修改、删除、查看解析、下载试卷材料和答案 | `PapersView.vue` |
| F090-F095 | 音乐/美术测评发布与撤回 | `AssessmentsView.vue` |
| F096 | 查看学生课外材料、作品、AI 辅助分析和评分要点 | `TeacherStudentsView.vue`、`GradingView.vue` |
| F097 | 查看学生测评成绩 | `ScoresView.vue` |
| F098-F100 | 平时表现补录、模板下载、线下成绩导入 | `ScoresView.vue` |
| F101-F103 | 学生证书查看、全部成绩导出和证书下载 | `CertificatesView.vue`、`TeacherStudentsView.vue`、`ScoresView.vue` |
| F104-F105 | 教师个人资料查看和修改 | `ProfileView.vue` |

## 页面质量

- 页面统一使用权限路由和角色菜单。
- 列表支持筛选、分页、加载中、空数据和错误提示。
- 高风险操作有二次确认或必填原因。
- 学生答题支持服务器时间、倒计时、15 秒自动保存、页面隐藏保存、文件上传、音频试听和图片资源。
- 练习和正式测评使用答卷 ID 恢复原答卷，交卷后生成逐题答案、解析和正确率。
- 教师评分保留学生答案、参考答案、评分量表、AI 辅助分和教师评语。
- 成绩、证书、报告和作品均提供空状态。
- 学生可查看趣味课堂课程和章节；教师可查看学生全部成绩和课外材料。

## 待后端联调

- 真实服务端权限与数据范围。
- 真实数据库 CRUD 和事务。
- 文件存储、签名 URL、音频与图片上传。
- 自动判分、人工评分、AI 分析和报告生成。
- 真实导入任务、证书任务和异常码。

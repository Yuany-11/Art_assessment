# 音频标签模型接入说明（arteval-v4）

## 定位

`arteval-v4` 是一个音乐音频标签模型（曲风 13 类、情绪 4 类、大小调、BPM），
仓库内另带一套规则参考分。它在本系统中的定位是**教学辅助标签**，不是评分器：

- 给教师展示学生音频作品的曲风、情绪、调式、BPM、削波/静音等客观信息；
- 给题库音频打标签，支持按曲风/情绪/BPM 检索和“相似音频题目”推荐；
- 给学生作品集提供标签归类和播放辅助。

模型不判断音准、节奏准确度、唱功或演奏技巧，也不接入任何成绩字段。

## 部署

1. 在 `arteval-v4` 目录创建虚拟环境（Python 3.10+，CPU 即可）：

   ```bash
   python -m venv .venv
   .venv\Scripts\pip install -r arteval-v4/requirements-service.txt
   ```

2. 启动推理服务（默认 `http://127.0.0.1:8100`）：

   ```bash
   arteval-v4\arteval-v4\start_service.bat
   ```

   或：

   ```bash
   .venv\Scripts\python arteval-v4\arteval-v4\service.py --port 8100
   ```

3. 后端 `.env` 配置：

   ```env
   AUDIO_TAGGER_ENABLED=true
   AUDIO_TAGGER_URL=http://127.0.0.1:8100
   AUDIO_TAGGER_TIMEOUT=120
   ```

   不部署模型时将 `AUDIO_TAGGER_ENABLED=false`，系统其余功能不受影响。

4. 批量补齐历史音频标签：

   ```bash
   python manage.py analyze_audio --dry-run
   python manage.py analyze_audio
   python manage.py analyze_audio --category student_work --limit 50
   ```

## 接口

| 接口 | 说明 |
| --- | --- |
| `GET /api/v1/files/{id}/audio-analysis` | 查询文件标签；学生看不到规则参考分 |
| `POST /api/v1/files/{id}/audio-analysis` | 生成或刷新标签，`{"force": true}` 强制重跑 |
| `POST /api/v1/grading/attempts/{id}/ai-suggestions` | 为音乐作品题生成 **AI 建议分**（0–题目满分），`{"force": true}` 强制重跑分析 |
| `GET /api/v1/questions?genre=Pop&emotion=happy` | 按音频标签过滤题目 |
| `GET /api/v1/questions/{id}/similar-audio?limit=5` | 按曲风/情绪/调式/BPM 距离推荐相似音频题 |

## AI 建议分（2026-11-13 重新接入）

当前版本没有原文档假设的 8090 DSP 服务，也没有后端第二套评分规则。为避免
「模型算一遍、后端规则再算一遍」的双重复核，AI 建议分的唯一口径是
arteval-v4（8100）的**校准后参考分**：

1. 8100 按 `scoring/rubric.calibrated.json` 输出 0–100 参考分；
2. 后端 `apps/exams/services/ai_scoring.py` 按 `参考分 / 100 × 本题满分` 折算，
   保留 2 位小数，并裁剪到 `0 ~ maxScore`；
3. 建议分只出现在教师评分页，点击「采用建议分」才会填入表单，
   仍需教师保存/终评后才写入成绩；
4. 后端**从不**读取建议分写 `AttemptAnswer.score` 或 `Score`，不存在覆盖人工分；
5. 置信度只用于提示「建议人工复核」，不会因为置信度低而压低建议分。

相关配置：

```env
AI_SCORE_SUGGESTION_ENABLED=true
AI_SCORE_CONFIDENCE_THRESHOLD=0.4
AI_SCORE_SOURCE_MAX=100
ARTEVAL_RUBRIC=scoring/rubric.calibrated.json   # 8100 服务侧读取
```

校准过程、样例对比表和已知局限见
[`docs/music-scoring-calibration.md`](music-scoring-calibration.md)。

题目列表、题目详情、评分任务详情和学生作品列表都会带 `audioTags` 字段；
题目详情的 `audioResources` 会逐个音频资源返回标签。

## 与现有功能的边界与冲突审计

| 现有功能 | 是否存在冲突 | 处理方式 |
| --- | --- | --- |
| AI 评分（已移除） | 有概念冲突 | 不恢复 `ScoringMode.AI`、`ai_score` 等字段，不写 `Attempt` / `AttemptAnswer` / `Score`；参考分只存 `AudioAnalysis.reference_score`，AI 建议分只在评分页展示，需教师点击「采用」并保存后才进入成绩 |
| 客观题自动判分 | 无 | 听赏题仍按标准答案判分，标签不参与判分 |
| 实践作品人工评分 | 无 | 标签只作评分页参考卡，教师仍逐题打分并终评 |
| 成绩、统计、排名、总评、证书 | 无 | 不读取 `AudioAnalysis`，不影响任何分数与等级 |
| 题库审核流转 | 无 | 生成标签不改变题目状态；标签只作为检索条件 |
| 自动/手动组卷 | 无 | 组卷不自动按标签抽题；“相似音频题目”只做人工参考 |
| 学生作品评分 | 无 | 只对音频作品展示标签；美术图片不进入分析；学生端不显示参考分 |
| 学习报告 | 无 | 现有报告仍由规则生成，本功能不写入报告 |
| 文件删除与权限 | 需处理 | 删除文件时同步逻辑删除分析记录；标签接口按上传人、任教班级/学科、学校范围校验 |
| 多格式音频 | 需降级 | WAV/MP3/OGG/FLAC 可直接分析；M4A/WEBM 依赖系统 ffmpeg，失败时记录 `failed`，不影响上传和其他功能 |
| BPM 倍频、中文音乐偏差 | 模型限制 | 标签和参考分明确标注“仅供教学参考”；不用于最终分类或成绩 |
| CPU 与并发 | 需限制 | 独立进程、串行推理、请求超时；只有用户点击“生成标签”或运行管理命令时才调用，交卷不受影响 |

## 准确度排查（2026-11-16）

- 启动时校验 checkpoint 标签顺序与 `training/infer.py` 的 `GENRES`/`EMOTIONS`；
- 长音频改为开头/中间/结尾分段聚合，结果带 `segments`；
- 置信度低于 0.4 的标签在教师端显示「不确定，建议人工判断」；
- BPM 标注为估计值；
- 回归工具与当前样例结果见
  [`docs/audio-tag-accuracy.md`](audio-tag-accuracy.md)。

## 已知限制

- 训练数据以欧美独立音乐为主，中文流行、民乐、戏曲会被映射到最近的类别；
- 曲风 13 类 top-1 约 63%，只适合预筛和检索；
- BPM 有倍频歧义，典型误差约 ±10 BPM；
- 情绪只有平静/欢快/悲伤/紧张四类；
- 不输出调性主音、乐器、人声检测，也不评价演唱/演奏水平；
- 规则参考分是研究性权重，不是官方评分标准。

# 美术作品 AI 辅助评分（建议分）

## 定位

美术作品题（`image_upload`）与拍照作答共用同一套图片答案结构。教师评分页的
「生成 AI 建议分」会返回：

- 折算到本题满分的 `suggestedScore`；
- 五个维度分：构图、色彩、造型/技法、完整性、创意表现；
- `confidence`、`needsReview`、`degraded` 与可解释分析文本。

**AI 分只是建议**，不会写入 `AttemptAnswer.score` / `Score`；教师点击「采用
建议分」并保存/终评后才进入成绩，教师手改的分始终优先。

## 当前实现：规则式降级

仓库内没有可用的美术评分模型权重，因此默认走可解释的规则式参考评分：

1. 读取学生上传的图片（本地媒体库或 MinIO）；作品题支持 1–3 张照片，
   AI 评分当前以答案主字段（第一张）为输入，其余照片供教师人工查看；
2. 计算亮度、对比度、色彩丰富度、清晰度、边缘平衡、画面有效内容比例、
   色相多样性等统计量；
3. 按 [`apps/exams/rules/art.yaml`](../apps/exams/rules/art.yaml) 的权重合成
   五个维度分和 0–100 参考分；
4. 按 `参考分 / 100 × 本题满分` 折算为建议分；
5. 返回 `degraded=true`、`method="rule_based"`、`confidence=0.35`，因此
   `needsReview=true`，前端始终显示「建议人工复核」和「规则式参考」标签。

这不是模型输出，也不能评价作品的艺术质量；它只用于给教师一个可解释的起点。

## 接入真实模型服务

在 `.env` 配置：

```env
ART_SCORER_ENABLED=true
ART_SCORER_URL=http://127.0.0.1:8100/art/score
ART_SCORER_TIMEOUT=60
ART_SCORER_CONFIDENCE_THRESHOLD=0.6
```

请求为 JSON：

```json
{"fileBase64": "...", "mimeType": "image/jpeg", "filename": "work.jpg"}
```

期望响应：

```json
{
  "score": 82.5,
  "confidence": 0.72,
  "grade": "良好",
  "dimensions": [
    {"key": "composition", "label": "构图", "score": 85, "weight": 0.25},
    {"key": "color", "label": "色彩", "score": 80, "weight": 0.2}
  ],
  "analysis": "……",
  "degraded": false
}
```

服务不可用或返回格式不正确时自动回退规则式结果并标记 `degraded=true`，
不会 500，也不影响人工评分。

## 接口

- `GET /api/v1/grading/attempts/{id}`：每题 `aiSuggestion` 直接带出美术建议分
  （只做本地规则计算，不访问外部服务）；
- `POST /api/v1/grading/attempts/{id}/ai-suggestions`：重新生成；美术题会按
  配置调用外部服务，失败自动降级。

## 边界

- 不修改客观题判分、多选题比例给分和音乐评分链路；
- 不自动覆盖教师已确认分数；
- 置信度低于 0.60 一律提示人工复核；
- 图片读取失败时返回 `status=failed` 和原因，不影响教师手动打分。

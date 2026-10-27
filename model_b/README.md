# 模型B｜美术测评与图像分析

美术作品四维评分服务 + 学情报告规则 + 四维评分模型训练链路。

## 1. 当前定位

- **scoring 服务当前仍使用启发式规则基线**（`app.py` 未接入训练权重），结果返回 `status=degraded`、`fallbackUsed=true`，**不冒充训练模型**。
- **四维评分模型已训练完成并通过验收**（v3.0，ResNet18 全参数微调，APDDv2 数据集）：去重测试集 1923 张，整体 MAE **7.21**（常数基线 10.94，阈值 8.5），四维全部低于基线。
- 权重在 `weights/apddv2_ft/best.pt`（44.8MB，不入库），训练产物在 `weights/apddv2_ft/说明.txt`、`logs/apddv2_ft/`。
- 把权重接入 `app.py` 是独立的一步（需加载 torch + 预处理 + 联调测试），当前未做；接入后 `status` 才可改为 `success`。

## 2. 启动

```bash
pip install -r requirements.txt
export INTERNAL_TOKEN=dev-token            # Windows PowerShell: $env:INTERNAL_TOKEN="dev-token"
export ALLOW_PRIVATE_URLS=true             # 仅本地演示需要（允许访问 127.0.0.1 样例图）
python -m uvicorn app:app --host 0.0.0.0 --port 8001
```

- 接口文档：`http://localhost:8001/docs`（Swagger 资源已本地化，无需外网）
- 健康检查：`GET /health`

## 3. 接口

### POST /api/v1/ai/art/score

请求头：`Content-Type: application/json`、`X-Internal-Token: <令牌>`

```json
{
  "imageUrl": "https://example.com/artwork.jpg",
  "workType": "painting",
  "studentId": 1001,
  "assessmentId": 12,
  "questionId": 3,
  "rubric": {"composition": 25, "color": 25, "modeling": 25, "creativity": 25},
  "requestId": "ai-art-20261023-0001"
}
```

响应（节选）：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "requestId": "ai-art-20261023-0001",
    "status": "degraded",
    "workType": "painting",
    "scores": {"composition": 78.5, "color": 86.0, "modeling": 80.5, "creativity": 84.5, "total": 82.38},
    "level": "good",
    "dimensionComments": {"composition": "...", "color": "...", "modeling": "...", "creativity": "..."},
    "strengths": ["色彩表现较好", "创意表现较好"],
    "improvements": ["加强细节刻画与形体边缘", "调整主体位置与画面疏密关系"],
    "summary": "作品整体完成度良好，色彩表现相对突出，构图仍有提升空间。",
    "fallbackUsed": true,
    "modelVersion": "art-baseline-v0.1.0",
    "costMs": 100
  }
}
```

错误码：

| 场景 | HTTP | 行为 |
|---|---|---|
| 缺少或错误 `X-Internal-Token` | 401 | 不返回分数 |
| 缺少必填字段 / rubric 总和≠100 | 400 | 不返回分数 |
| 非图片 / 非 http(s) / 内网地址 | 400 | 不返回分数 |
| 图片超过 10MB | 413 | 不返回分数 |
| 下载超时 / 下载失败 | 500 | 不返回分数 |

### POST /api/v1/ai/learning-report

规则生成，不涉及模型推理。输入 `studentId`、`subject`、`records`（含 `score`、`date`、`knowledgePoints`）、`timeRange`、`focus`、`language`；输出平均分、趋势、优势/薄弱点、建议与 `scoreTrend`。

## 4. 四维指标

| 维度 | 指标 |
|---|---|
| 构图 composition | 九宫格梯度能量、左右/上下平衡、对称性、重心偏移、留白 |
| 色彩 color | 平均饱和度、灰度对比度、Hasler 色彩丰富度、色相熵 |
| 造型 modeling | 拉普拉斯方差（清晰度）、边缘密度、梯度均值 |
| 创意 creativity | 色相多样性、不对称性、结构复杂度 |

总分：`total = Σ(维度分 × rubric权重) / 100`。等级：≥90 excellent、≥75 good、≥60 pass、<60 fail。

## 5. 已知局限

- 线上服务当前为规则基线；创意维度为启发式近似，不能等同教师判断。
- 构图分按画面内容强度加权，纯色/大面积留白作品会被显著压低。
- 评分只作辅助，正式成绩由业务规则合并。

## 5.1 四维评分模型 v3.0（已训练，待接入服务）

| 项 | 值 |
|---|---|
| 数据 | APDDv2（NeurIPS 2024），内容去重后 9672 张，train/val/test = 6596/1153/1923 |
| 模型 | ResNet18 全参数微调，分层学习率（主干 2e-4 / 评分层 1e-3），输入 224px |
| 损失 | 掩码 SmoothL1，缺失维度跳过；创意权重 1.5 |
| 训练 | GPU 19.3 分钟，13 轮早停，最优第 9 轮 |
| 测试 MAE | 构图 7.15 / 色彩 7.21 / 造型 6.99 / 创意 7.48 / 整体 **7.21** |
| 常数基线 | 构图 10.87 / 色彩 10.85 / 造型 11.40 / 创意 10.63 / 整体 10.94 |

对比 v2.0（冻结特征 + 岭回归，同一去重 1923 测试集）：整体 8.23 → 7.21，创意 8.86 → 7.48。
v2.0 早期报告的 8.01 是在未去重的 1993 张上得到，含数据泄漏，不可作为交付口径。

复现：`cd training && python train_apddv2_finetune.py --yes`（需要 APDDv2 图像与 CSV）。
限制：APDDv2 标注对象是专业绘画作品，不是儿童画；对儿童画只能作辅助参考，正式评分仍需教师复核。

## 6. 训练模块（画风分类）

```bash
cd training
python download_data.py    # 从 WikiArt 公开分类页下载 8 类画风图片（约 800 张）
python train.py            # ResNet18 微调，CPU 可跑
```

产出在 `training/runs/`：`train_log.txt`、`history.json`、`curves.png`、`confusion_matrix.png`、`best.pt`。

数据与权重不入库（见 `.gitignore`）。

## 7. 接入 v3.0 权重到服务（待做）

1. 在 `app.py` 启动时按需加载 `weights/apddv2_ft/best.pt`（torch + ResNet18 结构）；
2. 图片预处理与服务一致：resize 224、ToTensor、ImageNet 归一化；
3. 把 `scoring.score_image` 的返回值替换为模型四维输出，接口字段与返回结构不变；
4. 加载失败或推理异常时回退规则基线，保持 `fallbackUsed=true`；
5. 联调通过后把 `status` 改为 `success`，并更新 `modelVersion` 为 `art-cnn-apddv2-v3.0`。

# 模型评分规则库

本目录存放音乐、美术模型评分的 **YAML 规则**。后端在
`exams/services/scoring_rules.py` 中加载、校验、插值并计分；模型服务只负责
输出 0-1 的能力指标，不直接决定最终分数。

## 文件

| 文件 | 学科 | 类别 |
| --- | --- | --- |
| `music.yaml` | 音乐 | `vocal` 声乐、`instrumental` 器乐、`solfege` 视唱练耳、`theory` 乐理 |
| `art.yaml` | 美术 | `sketch` 素描、`color` 色彩、`quick_sketch` 速写、`calligraphy` 书法、`children` 儿童画 |
| `teacher_total.yaml` | 教师总评 | 平时测试、正式测评、证书的默认权重与等级折算 |

`music.yaml` / `art.yaml` 是模型评分规则；`teacher_total.yaml` 是教师总评的
默认值，教师可在接口中按班级/学期覆盖，不影响模型评分规则。

## 结构

```yaml
meta:
  id: music                 # 必须与文件名一致
  version: "1.0.0"          # 修改规则时递增，结果会带 ruleVersion
  standard: 社会艺术水平考级（通用基线）
  defaultBandCutoffs:       # 未指定级别时的优秀/良好/合格线
    excellent: 0.90
    good: 0.80
    pass: 0.60
levels:
  "5":
    label: 五级
    stage: 中级
    expectation: 该级别的能力描述
    bandCutoffs: {excellent: 0.90, good: 0.80, pass: 0.60}
anchorProfiles:             # 指标值 -> 得分比例，分段线性插值
  standard: [[0, 0], [0.40, 0.30], ...]
categories:
  vocal:
    dimensions:
      - key: pitch
        name: 音准
        weight: 0.25        # 同一类别内权重之和必须为 1
        metric: pitchAccuracy
        anchor: strict
        required: true
        descriptors: {excellent: ..., good: ..., pass: ..., fail: ...}
    caps:                   # 硬性封顶，可防止“其他项高分掩盖致命缺陷”
      - metric: pitchAccuracy
        op: lt              # lt / lte / gt / gte
        value: 0.50
        maxRatio: 0.50
        reason: 音准未达到基本要求，总分封顶 50%。
```

## 计分流程

1. 校验指标在 0-1 之间；未知指标忽略并给出 warning。
2. 按 `anchorProfiles[dim.anchor]` 把指标插值成维度得分比例。
3. 按 `weight` 加权汇总；缺少必填指标时 `totalScore=null`、转人工复核。
4. 依次应用 `caps`，命中则压低总分并写入 `capsApplied`。
5. 按级别 `bandCutoffs` 判定优秀/良好/合格/不合格。
6. 置信度低于 0.60 时标记 `needsManualReview=true`。

## 模型输出约定

模型服务收到请求中的 `scoringRules` 后，应返回：

```json
{
  "category": "vocal",
  "level": 5,
  "confidence": 0.86,
  "metrics": {
    "pitchAccuracy": 0.92,
    "rhythmAccuracy": 0.88,
    "timbreQuality": 0.85,
    "dictionClarity": 0.90,
    "expression": 0.84
  },
  "analysis": "音准稳定，乐句处理完整。",
  "evidence": {}
}
```

后端检测到 `metrics` 后会调用规则库重算分数，覆盖模型返回的 `score`；
只有 `score` 没有 `metrics` 时，仍以模型分为建议值。

## 题目侧声明

题目的 `answer` 中可加入：

```json
{"_ruleContext": {"category": "vocal", "level": 5}}
```

组卷、发布测评、开始答题的快照会自动带出 `ruleContext`。未声明时按题干
关键词推断；仍无法判断则把整科规则下发给模型，由模型返回 `category`。

## 校准建议

- 本规则是通用基线，不是考级机构官方大纲。选定机构后，按该机构大纲调整
  `weights`、`anchors`、`caps` 和各级 `bandCutoffs`。
- 每次调整递增 `meta.version`，便于成绩追溯与 A/B 对比。
- 上线前抽取不少于 30 份真实作品，由教研盲评，与规则分做一致性分析；
  偏差集中在某个维度时优先调整该维度的锚点。
- 修改 YAML 后无需重启，服务按文件 mtime 自动重新加载；语法或权重错误会
  在首次请求时抛出 `RuleConfigError`，部署时应先跑
  `manage.py test exams.tests.test_scoring_rules`。

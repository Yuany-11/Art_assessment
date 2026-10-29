"""模型B v3.0 + Pencils 创意头 本地上传测试窗口。

只读 weights/apddv2_ft/best.pt、weights/pencils_creativity/head.npz
与 calibration.json，浏览器拖图即出分。
创意维用 Pencils 儿童专家分线性头，其余三维仍用 v3.0。
不写文件、不接业务服务。
启动：art_assessment_gpu\\python.exe test_ui_v3.py
"""
import base64
import io
import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import numpy as np
import torch
import torch.nn as nn
from PIL import Image, ImageOps
from torchvision import transforms
from torchvision.models import resnet18

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[1]))
# 页面“快速示例”只读白名单，不开放任意路径
SAMPLES = {
    "child": HERE / "示例图" / "儿童示例_初中生.jpg",
    "pro": HERE / "示例图" / "专业示例_炭笔人像.jpg",
    "doc": HERE / "screenshots" / "backend_swagger.png",
}
CKPTS = [Path(p) for p in os.getenv(
    "ART_WEIGHT", str(ROOT / "weights" / "apddv2_ft" / "best.pt")).split(",") if p.strip()]
_HEAD_ENV = os.getenv("ART_HEAD", str(ROOT / "weights" / "pencils_creativity" / "head.npz"))
HEAD_PATH = None if _HEAD_ENV.strip().lower() in ("", "off", "none", "0") else Path(_HEAD_ENV)
CALIB_PATH = Path(os.getenv("ART_CALIB", HERE / "calibration_v31.json"))
CALIB_OLD = HERE / "calibration.json"
MAX_BYTES = 15 * 1024 * 1024
MIN_SIDE = 200

DIMS = ("composition", "color", "modeling", "creativity")
DIM_CN = {"composition": "构图", "color": "色彩", "modeling": "造型", "creativity": "创意"}

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
ckpts = [torch.load(p, map_location="cpu", weights_only=False) for p in CKPTS]
models = []
for _c in ckpts:
    _m = resnet18(weights=None)
    _m.fc = nn.Linear(_m.fc.in_features, len(DIMS))
    _m.load_state_dict(_c["state_dict"])
    models.append(_m.eval().to(device))
model = models[0]
trunks = [nn.Sequential(*list(m.children())[:-1]).eval().to(device) for m in models]
trunk = trunks[0]

HEAD = np.load(HEAD_PATH) if HEAD_PATH is not None and HEAD_PATH.exists() else None
if HEAD is not None:
    HEAD_MU, HEAD_SD = HEAD["mu"], HEAD["sd"]
    HEAD_W, HEAD_YM = HEAD["w"], float(HEAD["ym"][0])
VERSION = "+".join(c.get("version", "unknown") for c in ckpts) + \
    ("+pencils-creativity-v1" if HEAD is not None else "")
POLICY_VERSION = "student-calibration-v2" if CALIB_PATH.exists() else "percentile-v1"

if CALIB_PATH.exists():
    CALIB = json.loads(CALIB_PATH.read_text(encoding="utf-8"))
elif CALIB_OLD.exists():
    CALIB = json.loads(CALIB_OLD.read_text(encoding="utf-8"))
else:
    CALIB = None
if CALIB and str(CALIB.get("source", "")).startswith("v3.1"):
    VERSION += "+calib-v31"
LEVEL_FLOOR = (CALIB or {}).get("level_floor", {})
EXCELLENT_MIN_TECH = float(LEVEL_FLOOR.get("excellent_min_tech", 0))
GOOD_MIN_TECH = float(LEVEL_FLOOR.get("good_min_tech", 0))

_NORM = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])

tf = transforms.Compose([
    transforms.Resize(int(224 * 1.14)),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    _NORM,
])

# 创意头训练时用的是 Resize(256)，与 v3 的 Resize(255) 差 1px，单走一条保持一致
tf_head = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    _NORM,
])


def _piecewise(x, xs, ys):
    if x <= xs[0]:
        j = next((i for i in range(1, len(xs)) if xs[i] != xs[0]), None)
        if j is None:
            return ys[0]
        k = (ys[j] - ys[0]) / (xs[j] - xs[0])
        return max(0.0, ys[0] + (x - xs[0]) * k)
    if x >= xs[-1]:
        j = next((i for i in range(len(xs) - 2, -1, -1) if xs[i] != xs[-1]), None)
        if j is None:
            return ys[-1]
        k = (ys[-1] - ys[j]) / (xs[-1] - xs[j])
        return min(100.0, ys[-1] + (x - xs[-1]) * k)
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            if xs[i + 1] == xs[i]:
                return ys[i + 1]
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + t * (ys[i + 1] - ys[i])
    return x


def calibrate(scores):
    if not CALIB:
        return list(scores)
    tg = CALIB["targets"]
    ys = [tg["p05"], tg["p25"], tg["p50"], tg["p75"], tg["p95"]]
    out = []
    for d, v in zip(DIMS, scores):
        a = CALIB["dims"][d]
        xs = [a["p05"], a["p25"], a["p50"], a["p75"], a["p95"]]
        out.append(round(_piecewise(v, xs, ys), 1))
    return out


def _text_like(mask):
    on = mask.mean(axis=1) > 0.01
    edges = np.flatnonzero(np.diff(np.r_[False, on, False]))
    starts, ends = edges[0::2], edges[1::2]
    if len(starts) < 4:
        return False
    heights = (ends - starts).astype(np.float64)
    if heights.mean() >= 30:
        return False
    cv_h = heights.std() / max(heights.mean(), 1e-6)
    if cv_h >= 0.35:
        return False
    counts = []
    for s, e in zip(starts, ends):
        for y in range(int(s), int(e)):
            cut = np.diff(np.r_[False, mask[y], False])
            counts.append(len(np.flatnonzero(cut)[0::2]))
    return bool(counts) and float(np.median(counts)) >= 8


def _long_lines(mask, frac=0.8):
    count = 0
    for line in mask:
        edges = np.flatnonzero(np.diff(np.r_[False, line, False]))
        if len(edges) and int((edges[1::2] - edges[0::2]).max()) >= frac * line.size:
            count += 1
    return count


def detect_flags(img):
    """识别非绘画内容：文字文档、界面截图、数值异常图、分辨率过低。

    不能只看“白底黑线”：儿童线稿也是白底黑线，会被误杀。
    文字再要求成多条细横带、行高一致、每行大量笔画交替（runs_row）；
    线稿的横带高度不均，每行只有 2-4 段墨迹。
    截图要求至少有 3 条贯穿 80% 宽或高的直线；带边框的线稿只有 1 条。
    """
    flags = []
    a = np.asarray(img.convert("RGB"), dtype=np.uint8)
    if a.size == 0:
        return ["blank"]
    mx = a.max(axis=2).astype(np.int16)
    mn = a.min(axis=2).astype(np.int16)
    sat = float((mx - mn).mean())
    gray = a.mean(axis=2)
    white = float((gray > 240).mean())
    mid = float(((gray > 80) & (gray < 200)).mean())
    darkpix = float((gray < 128).mean())
    sm = np.asarray(
        img.convert("RGB").resize((min(512, img.width), min(512, img.height))),
        dtype=np.uint8,
    )
    packed = sm[:, :, 0].astype(np.uint32) * 65536 + sm[:, :, 1].astype(np.uint32) * 256 + sm[:, :, 2]
    vals, counts = np.unique(packed, return_counts=True)
    bg = vals[counts.argmax()].item()
    bgc = np.array([(bg >> 16) & 255, (bg >> 8) & 255, bg & 255], dtype=np.int16)
    ink = float((np.abs(sm.astype(np.int16) - bgc).max(axis=2) > 12).mean())

    if ink < 0.002 or gray.std() < 4:
        flags.append("blank")
    else:
        g = np.asarray(img.convert("L").resize((min(512, img.width), min(512, img.height))),
                       dtype=np.float32)
        dark = g < 128
        bg_share = float(counts.max() / packed.size)
        is_text = False
        if sat < 12 and white > 0.55 and mid < 0.18:
            is_text = _text_like(dark)
        elif darkpix > 0.5 and bg_share > 0.5:
            is_text = _text_like(~dark)

        if is_text:
            flags.append("document")
        else:
            gx = np.abs(np.diff(g, axis=1))[:, :-1]
            gy = np.abs(np.diff(g, axis=0))[:-1, :]
            h, w = min(gx.shape[0], gy.shape[0]), min(gx.shape[1], gy.shape[1])
            gx, gy = gx[:h, :w], gy[:h, :w]
            strong = (gx + gy) > 24
            if strong.mean() > 0.01:
                axis = (gx > 3 * gy + 1) | (gy > 3 * gx + 1)
                if max(_long_lines(axis), _long_lines(axis.T)) >= 3:
                    flags.append("screenshot")
    if min(img.size) < MIN_SIDE:
        flags.append("low_res")
    return flags


def _variants(img):
    w, h = img.size
    out = [img, img.transpose(Image.FLIP_LEFT_RIGHT)]
    dx, dy = int(w * 0.06), int(h * 0.06)
    if dx > 1 and dy > 1:
        out.append(img.crop((dx, dy, w - dx, h - dy)))
    return out


def score_image(img):
    img = ImageOps.exif_transpose(img)
    use_tta = os.getenv("ART_TTA", "1").lower() not in ("0", "false", "no")
    variants = _variants(img) if use_tta else [img]
    with torch.no_grad():
        acc, acc_creat, n = None, 0.0, 0
        for v in variants:
            x = tf(v).unsqueeze(0).to(device)
            for m in models:
                pred = m(x).clamp(0, 100)[0].float().cpu().numpy()
                acc = pred if acc is None else acc + pred
                n += 1
            if HEAD is not None:
                xh = tf_head(v).unsqueeze(0).to(device)
                for tr in trunks:
                    feat = tr(xh).flatten(1).cpu().numpy()[0]
                    acc_creat += float(((feat - HEAD_MU) / HEAD_SD) @ HEAD_W + HEAD_YM) * 25.0
        raw = (acc / n).tolist()
        if HEAD is not None:
            raw[3] = float(np.clip(acc_creat / n, 0.0, 100.0))
    raw = [round(v, 1) for v in raw]
    cal = calibrate(raw)
    total = round(sum(cal) / len(cal), 1)
    tech_min = min(cal[:3])
    if total >= 60:
        level = "pass"
    else:
        level = "fail"
    if total >= 75 and tech_min >= GOOD_MIN_TECH:
        level = "good"
    if total >= 90 and tech_min >= EXCELLENT_MIN_TECH:
        level = "excellent"
    level_capped = ((total >= 90 and tech_min < EXCELLENT_MIN_TECH) or
                    (total >= 75 and tech_min < GOOD_MIN_TECH))
    flags = detect_flags(img)
    not_art = "document" in flags or "screenshot" in flags or "blank" in flags
    return {
        "scores": {DIMS[i]: cal[i] for i in range(len(DIMS))},
        "rawScores": {DIMS[i]: raw[i] for i in range(len(DIMS))},
        "total": total,
        "rawTotal": round(sum(raw) / len(raw), 1),
        "level": "not_applicable" if not_art else level,
        "levelCapped": bool(level_capped and not not_art),
        "flags": flags,
        "minSide": min(img.size),
        "modelVersion": VERSION,
        "policyVersion": POLICY_VERSION,
    }


PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>模型B v3.0 美术四维评分测试</title>
<style>
  *{box-sizing:border-box}
  body{margin:0;padding:28px;background:#f5f7fa;color:#111827;
       font-family:"Microsoft YaHei","Segoe UI",sans-serif}
  h1{font-size:20px;margin:0 0 4px}
  .sub{color:#6b7280;font-size:13px;margin-bottom:18px}
  .wrap{display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start}
  .left{flex:1 1 320px;max-width:460px}
  #dz{border:2px dashed #cbd5e1;border-radius:12px;background:#fff;
      min-height:240px;display:flex;flex-direction:column;align-items:center;
      justify-content:center;color:#64748b;cursor:pointer;padding:16px;text-align:center}
  #dz.over{border-color:#3b82f6;background:#eff6ff}
  #dz b{font-size:15px;color:#334155}
  #preview{display:none;max-width:100%;max-height:420px;border-radius:10px;
           box-shadow:0 1px 3px rgba(0,0,0,.15)}
  .right{flex:1 1 420px;background:#fff;border-radius:12px;padding:18px 20px;
         box-shadow:0 1px 3px rgba(0,0,0,.07)}
  .total{display:flex;align-items:baseline;gap:12px;margin-bottom:14px}
  .total .n{font-size:44px;font-weight:800;line-height:1}
  .badge{padding:3px 12px;border-radius:999px;font-size:13px;font-weight:600}
  .excellent{background:#dcfce7;color:#166534}
  .good{background:#dbeafe;color:#1e40af}
  .pass{background:#fef3c7;color:#92400e}
  .fail{background:#fee2e2;color:#991b1b}
  .na{background:#e5e7eb;color:#374151}
  .row{margin:12px 0}
  .row .lab{display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px}
  .row .lab b{font-size:14px}
  .bar{height:10px;background:#eef2f7;border-radius:5px;overflow:hidden}
  .bar>i{display:block;height:100%;background:linear-gradient(90deg,#60a5fa,#22c55e)}
  .note{color:#9ca3af;font-size:12px;margin-top:16px;line-height:1.7}
  .warn{background:#fef3c7;color:#92400e;border-radius:8px;padding:10px 12px;
        font-size:13px;line-height:1.6;margin:8px 0}
  .warn.err{background:#fee2e2;color:#991b1b}
  #err{color:#b91c1c;font-size:13px;margin-top:8px;min-height:18px}
  #loading{display:none;color:#2563eb;font-size:13px;margin-top:8px}
  .meta{color:#6b7280;font-size:12px;margin-top:4px}
</style></head><body>
<h1>模型B · 美术作品四维评分（测试窗口）</h1>
<div class="sub">art-cnn-apddv2-v3.0 + pencils-creativity-v1 · ResNet18 微调 · 本机推理 · __DEVICE__ · 已按学生作品刻度校准</div>
<div class="wrap">
  <div class="left">
    <div id="dz" onclick="file.click()">
      <img id="preview" alt="预览">
      <div id="hint"><b>把图片拖到这里</b><div class="meta">或点击选择文件（JPG / PNG，≤15MB）</div></div>
    </div>
    <input id="file" type="file" accept="image/*" style="display:none">
    <div id="loading">正在推理…</div>
    <div id="err"></div>
  </div>
  <div class="right">
    <div id="warns"></div>
    <div class="total"><span class="n" id="total">—</span><span id="level"></span></div>
    <div id="rows"></div>
    <div class="note">
      构图/色彩/造型原始分是 APDDv2 艺术家刻度（中位数约 63–65）；创意维已换成 Pencils
      儿童专家分的线性头（5 折 CV Pearson +0.65），输出乘 25 到 0–100 后单独校准。
      四维按 raw 分位映射到学生档位（当前 v3.1 试评口径：p05/p25/p50/p75/p95 = 40/62/72/82/93），
      等级线 90/75/60。校准基准来自测试集预测分布，不是教师真实打分校准；创意头训练图是线稿，
      对彩绘儿童画属于外推。正式成绩仍需教师复核，单张结果不能作为准确率依据。
    </div>
  </div>
</div>
<script>
const dz=document.getElementById('dz'),file=document.getElementById('file');
const hint=document.getElementById('hint'),preview=document.getElementById('preview');
const err=document.getElementById('err'),loading=document.getElementById('loading');
const DIMS=[['composition','构图'],['color','色彩'],['modeling','造型'],['creativity','创意']];
dz.ondragover=e=>{e.preventDefault();dz.classList.add('over')};
dz.ondragleave=()=>dz.classList.remove('over');
dz.ondrop=e=>{e.preventDefault();dz.classList.remove('over');
  if(e.dataTransfer.files[0])handle(e.dataTransfer.files[0])};
file.onchange=()=>{if(file.files[0])handle(file.files[0])};
function showErr(m){err.textContent=m}
async function handle(f){
  if(!f.type.startsWith('image/')){showErr('请选择图片文件');return}
  const reader=new FileReader();
  reader.onload=async()=>{
    preview.src=reader.result;preview.style.display='block';hint.style.display='none';
    showErr('');loading.style.display='block';
    const t0=performance.now();
    try{
      const r=await fetch('/score',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({image:reader.result})});
      const j=await r.json();
      if(!r.ok)throw new Error(j.error||'评分失败');
      render(j,(performance.now()-t0).toFixed(0));
    }catch(e){showErr(e.message)}
    loading.style.display='none';
  };
  reader.readAsDataURL(f);
}
const LV={excellent:['优秀','excellent'],good:['良好','good'],pass:['合格','pass'],
          fail:['不合格','fail'],not_applicable:['不适用','na']};
function render(j,ms){
  const flags=j.flags||[];
  let warns='';
  if(flags.includes('document')){
    warns+='<div class="warn err"><b>疑似文字/文档，不是绘画作品。</b><br>'+
      '四维评分不适用，下面只显示模型原始输出，不应作为作品成绩。</div>';
  }else if(flags.includes('screenshot')){
    warns+='<div class="warn err"><b>疑似界面截图/非绘画内容。</b><br>'+
      '四维评分不适用，下面只显示模型原始输出，不应作为作品成绩。</div>';
  }else if(flags.includes('blank')){
    warns+='<div class="warn err"><b>图片近乎空白或内容过少。</b>四维评分不适用。</div>';
  }
  if(flags.includes('low_res')){
    warns+='<div class="warn"><b>图片分辨率偏低</b>（短边 '+j.minSide+'px）。'+
      '缩略图会明显拉低分数，请用原始作品图测试。</div>';
  }
  document.getElementById('warns').innerHTML=warns;
  if(flags.includes('document')||flags.includes('screenshot')||flags.includes('blank')){
    document.getElementById('total').textContent='—';
  }else{
    document.getElementById('total').textContent=j.total.toFixed(1);
  }
  const lv=LV[j.level]||['—','na'];
  document.getElementById('level').innerHTML='<span class="badge '+lv[1]+'">'+lv[0]+' · '+j.level+'</span>';
  document.getElementById('rows').innerHTML=DIMS.map(([k,cn])=>
    '<div class="row"><div class="lab"><span>'+cn+'</span><b>'+j.scores[k].toFixed(1)+
    '<span style="color:#9ca3af;font-weight:400;font-size:12px">（原始 '+j.rawScores[k].toFixed(1)+'）</span></b></div>'+
    '<div class="bar"><i style="width:'+j.scores[k]+'%"></i></div></div>').join('');
  document.getElementById('rows').insertAdjacentHTML('beforeend',
    '<div class="meta">原始总分 '+j.rawTotal.toFixed(1)+' · 推理 '+ms+' ms · 模型 '+j.modelVersion+'</div>');
}
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            tpl = HERE / "test_ui_template.html"
            page = tpl.read_text(encoding="utf-8") if tpl.exists() else PAGE
            html = (page.replace("__DEVICE__", str(device))
                        .replace("__VERSION__", VERSION))
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path in ("/old", "/old.html"):
            html = (PAGE.replace("__DEVICE__", str(device))
                        .replace("__VERSION__", VERSION))
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path in ("/compare", "/compare.html"):
            cmp_path = HERE / "test_ui_compare.html"
            if not cmp_path.exists():
                self._send(404, b'{"error":"compare page not found"}')
                return
            self._send(200, cmp_path.read_bytes(), "text/html; charset=utf-8")
        elif self.path.startswith("/sample/"):
            key = self.path[len("/sample/"):].split("?", 1)[0]
            path = SAMPLES.get(key)
            if path is None or not path.exists():
                self._send(404, b'{"error":"sample not found"}')
                return
            ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            self._send(200, path.read_bytes(), ctype)
        elif self.path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        if self.path != "/score":
            self._send(404, b'{"error":"not found"}')
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n <= 0 or n > MAX_BYTES * 2:
                self._send(413, b'{"error":"\xe5\x9b\xbe\xe7\x89\x87\xe5\xa4\xaa\xe5\xa4\xa7"}')
                return
            payload = json.loads(self.rfile.read(n).decode("utf-8"))
            raw = payload["image"]
            if "," in raw:
                raw = raw.split(",", 1)[1]
            img = Image.open(io.BytesIO(base64.b64decode(raw))).convert("RGB")
            body = json.dumps(score_image(img), ensure_ascii=False).encode("utf-8")
            self._send(200, body)
        except Exception as exc:  # noqa: BLE001
            body = json.dumps({"error": f"评分失败：{exc}"}, ensure_ascii=False).encode("utf-8")
            self._send(400, body)

    def log_message(self, *args):
        pass


def main():
    port = int(os.getenv("ART_PORT", "8010"))
    host = os.getenv("ART_HOST", "127.0.0.1")
    try:
        srv = ThreadingHTTPServer((host, port), Handler)
    except OSError as exc:
        print(f"端口 {port} 被占用，无法启动：{exc}", flush=True)
        sys.exit(1)
    print(f"测试窗口已启动: http://127.0.0.1:{port}/", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()

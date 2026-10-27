"""模型B v3.0 本地上传测试窗口。

只读 weights/apddv2_ft/best.pt 与 calibration.json，浏览器拖图即出分。
不写文件、不接业务服务。
启动：art_assessment_gpu\\python.exe test_ui_v3.py
"""
import base64
import io
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms
from torchvision.models import resnet18

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[1]))
CKPT = Path(os.getenv("ART_WEIGHT", ROOT / "weights" / "apddv2_ft" / "best.pt"))
CALIB_PATH = Path(os.getenv("ART_CALIB", HERE / "calibration.json"))
MAX_BYTES = 15 * 1024 * 1024
MIN_SIDE = 200

DIMS = ("composition", "color", "modeling", "creativity")
DIM_CN = {"composition": "构图", "color": "色彩", "modeling": "造型", "creativity": "创意"}

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
ckpt = torch.load(CKPT, map_location="cpu", weights_only=False)
model = resnet18(weights=None)
model.fc = nn.Linear(model.fc.in_features, len(DIMS))
model.load_state_dict(ckpt["state_dict"])
model.eval().to(device)
VERSION = ckpt.get("version", "unknown")

CALIB = json.loads(CALIB_PATH.read_text(encoding="utf-8")) if CALIB_PATH.exists() else None

tf = transforms.Compose([
    transforms.Resize(int(224 * 1.14)),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])


def _piecewise(x, xs, ys):
    if x <= xs[0]:
        k = (ys[1] - ys[0]) / (xs[1] - xs[0])
        return max(0.0, ys[0] + (x - xs[0]) * k)
    if x >= xs[-1]:
        k = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
        return min(100.0, ys[-1] + (x - xs[-1]) * k)
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
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


def looks_like_document(img):
    """白底黑字类文字/文档图：近乎无彩色、大面积近白、缺少中间灰。"""
    a = np.asarray(img.convert("RGB"), dtype=np.uint8)
    if a.size == 0:
        return False
    mx = a.max(axis=2).astype(np.int16)
    mn = a.min(axis=2).astype(np.int16)
    sat = float((mx - mn).mean())
    gray = a.mean(axis=2)
    white = float((gray > 240).mean())
    mid = float(((gray > 80) & (gray < 200)).mean())
    return sat < 12 and white > 0.55 and mid < 0.18


def score_image(img):
    raw = None
    with torch.no_grad():
        x = tf(img).unsqueeze(0).to(device)
        raw = model(x).clamp(0, 100)[0].float().cpu().tolist()
    raw = [round(v, 1) for v in raw]
    cal = calibrate(raw)
    total = round(sum(cal) / len(cal), 1)
    if total >= 90:
        level = "excellent"
    elif total >= 75:
        level = "good"
    elif total >= 60:
        level = "pass"
    else:
        level = "fail"
    flags = []
    if looks_like_document(img):
        flags.append("document")
    if min(img.size) < MIN_SIDE:
        flags.append("low_res")
    return {
        "scores": {DIMS[i]: cal[i] for i in range(len(DIMS))},
        "rawScores": {DIMS[i]: raw[i] for i in range(len(DIMS))},
        "total": total,
        "rawTotal": round(sum(raw) / len(raw), 1),
        "level": "not_applicable" if "document" in flags else level,
        "flags": flags,
        "minSide": min(img.size),
        "modelVersion": VERSION,
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
<div class="sub">art-cnn-apddv2-v3.0 · ResNet18 微调 · 本机推理 · __DEVICE__ · 已按学生作品刻度校准</div>
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
      模型原始分是 APDDv2 艺术家刻度（四维中位数约 63–65），已按分位数校准到学生作品档位
      （约 5% 不合格、25% 合格、50% 良好、20% 优秀）。校准基准来自 1923 张测试图的预测分布，
      不是教师真实打分校准；正式成绩仍需教师复核，单张结果不能作为准确率依据。
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
  }
  if(flags.includes('low_res')){
    warns+='<div class="warn"><b>图片分辨率偏低</b>（短边 '+j.minSide+'px）。'+
      '缩略图会明显拉低分数，请用原始作品图测试。</div>';
  }
  document.getElementById('warns').innerHTML=warns;
  if(flags.includes('document')){
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
            html = PAGE.replace("__DEVICE__", str(device))
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
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
    srv = None
    for port in range(8010, 8020):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            print(f"测试窗口已启动: http://127.0.0.1:{port}/", flush=True)
            break
        except OSError:
            continue
    if srv is None:
        print("8010-8019 端口都被占用", flush=True)
        sys.exit(1)
    srv.serve_forever()


if __name__ == "__main__":
    main()

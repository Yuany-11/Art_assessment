"""中国学生作品 4 档人工点评页（本地 127.0.0.1）。

31 幅攀枝花市 2025 中小学生美术比赛一等奖作品（初中/高中），
右侧固定四档标准；键盘 1-4 打分，u 撤回上一张，自动保存可续点。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
IMG = ROOT / "data" / "10_cn_mid" / "images"
OUT = ROOT / "logs" / "cn_mid_eval"
VOTES = OUT / "human_votes.jsonl"
PICK = [0, 1, 2, 3, 6, 7, 16, 17, 18, 19, 20, 21, 22, 24, 25, 26, 27, 28, 29,
        30, 31, 32, 33, 34, 36, 37, 38, 39, 40, 41]
LEVELS = ("excellent", "good", "pass", "fail")


def manifest():
    return [{"path": str(IMG / f"pzh_{i:03d}.jpeg"), "name": f"pzh_{i:03d}"} for i in PICK]


PAGE = """<!doctype html><html lang="zh"><meta charset="utf-8">
<title>中国学生作品 四档点评</title>
<style>
*{box-sizing:border-box}
body{font-family:system-ui,"Microsoft YaHei";margin:0;background:#f4f5f7;height:100vh;display:flex}
#main{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;position:relative}
img{max-width:min(62vw,860px);max-height:70vh;box-shadow:0 2px 14px #0002;background:#fff}
.bar{margin-top:14px;display:flex;gap:10px}
button{font-size:17px;padding:10px 20px;border:0;border-radius:8px;cursor:pointer;background:#fff;box-shadow:0 1px 4px #0002}
button:hover{background:#eef}
.meta{margin-top:10px;color:#555;font-size:14px}
progress{width:min(52vw,520px);height:8px}
#std{width:430px;background:#fff;border-left:1px solid #ddd;padding:18px 20px;overflow:auto;font-size:13.5px;line-height:1.55}
#std h3{margin:0 0 8px;font-size:16px}
#std table{border-collapse:collapse;width:100%;margin-bottom:10px}
#std th,#std td{border:1px solid #e2e4e8;padding:5px 6px;vertical-align:top}
#std th{background:#f0f3f8;font-weight:600}
#std .hint{color:#a33}
</style>
<body>
<div id="main">
  <div class="meta" id="meta"></div>
  <img id="im" src="">
  <div class="bar" id="bar"></div>
  <div class="meta">1 优秀 / 2 良好 / 3 合格 / 4 不合格　u 撤回上一张　5 跳过</div>
  <progress id="pg" value="0" max="1"></progress>
</div>
<div id="std">
  <h3>四档标准（以“大多数初中生正常水平”为参照）</h3>
  <table>
    <tr><th>档位</th><th>画面表现</th></tr>
    <tr><td><b>优秀 90+</b><br>年级内突出</td><td>构图有主次、空间、节奏的主动设计；色彩统一且有变化，能表达情绪；造型比例结构准确、有细节质感；有明确个人表达或独特视角。</td></tr>
    <tr><td><b>良好 75–89</b><br>明显高于一般</td><td>有明确主体和重心，前后疏密有安排；有主色调，冷暖/明暗有意识；比例结构基本准确，有细节；有个人选取或组合，不是纯模仿。</td></tr>
    <tr><td><b>合格 60–74</b><br>大多数初中生正常水平</td><td>主体能放进画面、位置基本合理；用了多种颜色、涂色基本完整；形象可辨、比例有偏差；按常见题材或范例完成。</td></tr>
    <tr><td><b>不合格 &lt;60</b><br>明显低于一般</td><td>画面未完成、主体难辨、涂色大面积缺失、明显敷衍。</td></tr>
  </table>
  <div class="hint">校准：优秀应是少数（普通班通常不到两成），良好以上别超过一半；本批是获奖作品，整体会偏高，请按“档位描述”而不是“和我见过的最好作品比”。</div>
  <p style="color:#666">来源：攀枝花市 2025 年中小学生艺术专场比赛美术一等奖作品（初中、高中篇）。</p>
</div>
<script>
let M=[],votes={},i=0,order=[];
const L=[["excellent","优秀"],["good","良好"],["pass","合格"],["fail","不合格"]];
async function boot(){
  M=await (await fetch('/manifest')).json();
  votes=await (await fetch('/votes')).json();
  i=M.findIndex(m=>!(m.path in votes)); if(i<0)i=M.length;
  L.forEach(([k,label],n)=>{const b=document.createElement('button');
    b.textContent=(n+1)+' '+label; b.onclick=()=>cast(k); document.getElementById('bar').appendChild(b);});
  show();
}
function show(){
  document.getElementById('pg').max=M.length;
  document.getElementById('pg').value=Object.keys(votes).length;
  if(i>=M.length){document.getElementById('im').style.display='none';
    document.getElementById('meta').textContent='全部完成 ✅ 共 '+M.length+' 幅，可以关掉页面';return;}
  const m=M[i]; document.getElementById('im').src='/img/'+i;
  document.getElementById('meta').textContent='第 '+(i+1)+' / '+M.length+' 幅　'+m.name;
}
async function cast(k){
  if(i>=M.length)return;
  votes[M[i].path]=k; order.push(i);
  await fetch('/vote',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({path:M[i].path,level:k})});
  i++; show();
}
function undo(){ if(!order.length)return; const j=order.pop(); delete votes[M[j].path]; i=j;
  fetch('/unvote',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:M[j].path})}); show(); }
document.addEventListener('keydown',e=>{
  const n={'1':0,'2':1,'3':2,'4':3}[e.key];
  if(n!==undefined)cast(L[n][0]); else if(e.key==='5'){i++;show();} else if(e.key.toLowerCase()==='u')undo();
});
boot();
</script></body></html>"""


def make_app():
    items = manifest()

    def read_votes():
        d = {}
        if VOTES.exists():
            for line in VOTES.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    d[r["path"]] = r["level"]
        return d

    def write_votes(d):
        OUT.mkdir(parents=True, exist_ok=True)
        VOTES.write_text("".join(json.dumps({"path": p, "level": lv, "ts": time.time()},
                                            ensure_ascii=False) + "\n" for p, lv in d.items()),
                         encoding="utf-8")

    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def index():
        return PAGE

    @app.get("/manifest")
    def mans():
        return items

    @app.get("/votes")
    def votes():
        return read_votes()

    @app.get("/img/{idx}")
    def img(idx: int):
        if not 0 <= idx < len(items):
            raise HTTPException(404)
        p = Path(items[idx]["path"])
        if not p.exists():
            raise HTTPException(404)
        return Response(p.read_bytes(), media_type="image/jpeg")

    @app.post("/vote")
    def vote(body: dict):
        path, level = body.get("path"), body.get("level")
        if level not in LEVELS or not any(x["path"] == path for x in items):
            raise HTTPException(400)
        d = read_votes()
        d[path] = level
        write_votes(d)
        return {"ok": True}

    @app.post("/unvote")
    def unvote(body: dict):
        d = read_votes()
        d.pop(body.get("path"), None)
        write_votes(d)
        return {"ok": True}

    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8764)
    args = ap.parse_args()
    import uvicorn
    uvicorn.run(make_app(), host="127.0.0.1", port=args.port, log_level="warning")

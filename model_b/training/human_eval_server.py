"""初中/小学画 4 档人工点评页（本地，127.0.0.1）。

120 张（初中 90 + 小学 30），键盘 1-4 打分，自动保存、可断点续点。
用法：python training/human_eval_server.py --port 8763
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
KIDO = ROOT / "data" / "09_kido" / "Dataset" / "Images" / "Education"
OUT = ROOT / "logs" / "mid_school_eval"
MANIFEST = OUT / "manifest.json"
VOTES = OUT / "human_votes.jsonl"

LEVELS = [("excellent", "优秀"), ("good", "良好"), ("pass", "合格"), ("fail", "不合格")]


def build_manifest(n_sec=90, n_pri=30, seed=20261029):
    rng = random.Random(seed)
    items = []
    for group, n in (("Secondary", n_sec), ("Primary", n_pri)):
        paths = sorted(p for p in KIDO.rglob("*.jpg") if p.parent.name == group)
        rng.shuffle(paths)
        for p in paths[:n]:
            items.append({"group": group, "path": str(p), "name": p.name})
    OUT.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return items


PAGE = """<!doctype html><html lang="zh"><meta charset="utf-8">
<title>初中画档位点评</title>
<style>
body{font-family:system-ui,"Microsoft YaHei";margin:0;background:#f4f5f7;display:flex;flex-direction:column;
align-items:center;justify-content:center;height:100vh;user-select:none}
img{max-width:min(72vw,980px);max-height:66vh;box-shadow:0 2px 14px #0002;background:#fff}
.bar{margin-top:16px;display:flex;gap:12px}
button{font-size:19px;padding:12px 26px;border:0;border-radius:8px;cursor:pointer;background:#fff;
box-shadow:0 1px 4px #0002}
button:hover{background:#eef}button.k{background:#2b6cb0;color:#fff}
.meta{margin-top:12px;color:#555;font-size:14px}progress{width:min(60vw,600px);height:10px}
</style>
<body>
<div class="meta" id="meta"></div>
<img id="im" src="">
<div class="bar" id="bar"></div>
<div class="meta">按 1 优秀 / 2 良好 / 3 合格 / 4 不合格；5 跳过；图片下不动就是加载失败，按 5 跳过</div>
<progress id="pg" value="0" max="1"></progress>
<script>
let M=[],votes={},i=0;
const L=[["excellent","优秀"],["good","良好"],["pass","合格"],["fail","不合格"]];
async function boot(){
  M=await (await fetch('/manifest')).json();
  const v=await (await fetch('/votes')).json();
  votes=v; const done=Object.keys(votes).length;
  i=M.findIndex(m=>!(m.path in votes)); if(i<0)i=M.length;
  L.forEach(([k,label],n)=>{const b=document.createElement('button');
    b.textContent=(n+1)+' '+label; b.onclick=()=>cast(k); document.getElementById('bar').appendChild(b);});
  show();
}
function show(){
  const pg=document.getElementById('pg'); pg.max=M.length; pg.value=Object.keys(votes).length;
  if(i>=M.length){document.getElementById('im').style.display='none';
    document.getElementById('meta').textContent='全部完成 ✅ 共 '+M.length+' 张，可以关掉页面了';return;}
  const m=M[i]; document.getElementById('im').src='/img/'+i;
  document.getElementById('meta').textContent=
    '第 '+(i+1)+' / '+M.length+' 张　'+(m.group==='Secondary'?'初中':'小学')+'　'+m.name;
}
async function cast(k){
  if(i>=M.length)return;
  votes[M[i].path]=k; await fetch('/vote',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({path:M[i].path,level:k})});
  i++; while(i<M.length && (M[i].path in votes)) i++; show();
}
document.addEventListener('keydown',e=>{
  const n={ '1':0,'2':1,'3':2,'4':3 }[e.key];
  if(n!==undefined)cast(L[n][0]); else if(e.key==='5'){i++;show();}
});
boot();
</script></body></html>"""


def make_app():
    app = FastAPI()
    items = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else build_manifest()

    def read_votes():
        d = {}
        if VOTES.exists():
            for line in VOTES.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    d[r["path"]] = r["level"]
        return d

    @app.get("/", response_class=HTMLResponse)
    def index():
        return PAGE

    @app.get("/manifest")
    def manifest():
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
        if level not in dict(LEVELS) or not any(x["path"] == path for x in items):
            raise HTTPException(400)
        if path not in read_votes():
            OUT.mkdir(parents=True, exist_ok=True)
            with VOTES.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"path": path, "level": level, "ts": time.time()},
                                   ensure_ascii=False) + "\n")
        return {"ok": True}

    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8763)
    args = ap.parse_args()
    if not MANIFEST.exists():
        build_manifest()
    import uvicorn
    uvicorn.run(make_app(), host="127.0.0.1", port=args.port, log_level="warning")

"""美术出题服务：FastAPI 封装，后端通过 HTTP 调用。"""
from __future__ import annotations

import json
import os
import random
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .runtime import QgenRuntime

app = FastAPI(title="Model B Question Generation", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
runtime = QgenRuntime(
    model_path=os.getenv("QGEN_MODEL"),
    adapter_path=os.getenv("QGEN_ADAPTER"),
    load_4bit=os.getenv("QGEN_LOAD_4BIT", "1") != "0",
    max_new_tokens=int(os.getenv("QGEN_MAX_NEW_TOKENS", "600")),
)


class GenerateRequest(BaseModel):
    unit_id: str
    knowledge_point: str
    type: str = Field(description="single_choice / true_false / fill_blank / short_answer")
    difficulty: int = Field(default=1, ge=1, le=3)


TEST_PAGE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>模型B · 出题测试页</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f6f8fa;--panel:#fff;--line:#d0d7de;--fg:#1f2328;--dim:#656d76;--ok:#1a7f37;--bad:#cf222e;--accent:#0969da}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
header{padding:16px 24px;background:var(--panel);border-bottom:1px solid var(--line)}
h1{font-size:18px;margin:0 0 4px}header p{margin:0;color:var(--dim);font-size:12px}
.wrap{max-width:1080px;margin:0 auto;padding:20px 24px;display:grid;
grid-template-columns:360px 1fr;gap:20px}
@media(max-width:860px){.wrap{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px}
label{display:block;font-size:12px;color:var(--dim);margin:10px 0 4px}
select,button,input{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:6px;
background:#fff;font-size:14px;color:var(--fg)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.grid2 label{margin:0}
button{margin-top:16px;background:var(--accent);border-color:var(--accent);color:#fff;
font-weight:600;cursor:pointer}
button:disabled{opacity:.55;cursor:wait}
.status{font-weight:600;margin-bottom:10px}
.status.ok{color:var(--ok)}.status.bad{color:var(--bad)}
.stem{font-size:16px;line-height:1.7;margin:6px 0 14px}
.opts{list-style:none;padding:0;margin:0 0 14px}
.opts li{padding:6px 10px;border:1px solid var(--line);border-radius:6px;margin-bottom:6px}
.opts li{cursor:pointer}
.opts li.sel{border-color:var(--accent);background:#ddf4ff}
button.tfbtn{width:auto;padding:6px 20px}
button.tfbtn.sel{background:var(--accent);border-color:var(--accent);color:#fff}
.opts li.right{border-color:var(--ok);background:#dafbe1}
.kv{margin:8px 0}.kv b{display:block;font-size:12px;color:var(--dim);font-weight:500}
.err{background:#ffebe9;border:1px solid #ffcecb;border-radius:6px;padding:10px;margin-bottom:12px;
color:var(--bad);font-size:13px;white-space:pre-wrap}
pre{background:#f6f8fa;border:1px solid var(--line);border-radius:6px;padding:10px;
font-size:12px;overflow:auto;max-height:360px;white-space:pre-wrap}
.muted{color:var(--dim);font-size:13px}
.tags{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.tag{font-size:12px;background:#ddf4ff;color:#0969da;border-radius:999px;padding:2px 10px}
</style></head><body>
<header><h1>模型B · 出题测试页</h1>
<p>Qwen2.5-3B-Instruct + LoRA v4 · 选择目录后生成，约 10 秒/题 · ok=true 只代表格式校验通过，内容仍需人工复核</p></header>
<div class="wrap">
  <div class="card">
    <label>年级</label><select id="grade"></select>
    <label>单元</label><select id="unit"></select>
    <label>知识点</label><select id="kp"></select>
    <label>题型</label><select id="type"></select>
    <label>难度</label><select id="diff"></select>
    <button id="go" onclick="gen()">生成题目</button>
    <label>快速组卷（从题库抽取，毫秒级）</label>
    <div class="grid2">
      <input id="n_sc" type="number" value="5" min="0" max="20" title="选择题数量">
      <input id="n_tf" type="number" value="5" min="0" max="20" title="判断题数量">
      <input id="n_fb" type="number" value="4" min="0" max="20" title="填空题数量">
      <input id="n_sa" type="number" value="2" min="0" max="20" title="解答题数量">
    </div>
    <p class="muted" style="margin:4px 0 0">数量依次为：选择 / 判断 / 填空 / 解答</p>
    <button onclick="paperGen()" style="background:#0969da;border-color:#0969da;margin-top:8px">快速组卷</button>
    <button onclick="loadDemo()" style="background:#1a7f37;border-color:#1a7f37;margin-top:8px">加载演示卷（已人工审校）</button>
    <label style="display:flex;align-items:center;gap:8px;margin-top:12px;color:var(--fg);font-size:13px">
      <input type="checkbox" id="studentMode" style="width:auto;margin:0" onchange="rerender()">
      学生答题模式（不返回答案，交卷后判分）
    </label>
    <p class="muted" id="hint">首次生成需要加载模型，可能多等 1–2 分钟。</p>
  </div>
  <div class="card" id="out"><p class="muted">结果会显示在这里。</p></div>
</div>
<script>
const $=id=>document.getElementById(id);
let CAT=null;
const TYPELABEL={single_choice:'选择',true_false:'判断',fill_blank:'填空',short_answer:'解答'};
const GRADELABEL={'1':'小学一年级','2':'小学二年级','3':'小学三年级','4':'小学四年级','5':'小学五年级','6':'小学六年级','7':'初中一年级','8':'初中二年级','9':'初中三年级'};
const gradeLabel=g=>GRADELABEL[g]||`${g} 年级`;
async function init(){
  const r=await fetch('/catalog'); CAT=await r.json();
  const grades=Object.keys(CAT.grades).sort((a,b)=>a-b);
  $('grade').innerHTML=grades.map(g=>`<option value="${g}">${gradeLabel(g)}</option>`).join('');
  $('grade').value=grades.includes('7')?'7':grades[0];
  $('grade').onchange=onGrade; $('unit').onchange=onUnit;
  onGrade();
}
function units(){ return CAT.grades[$('grade').value].units; }
function onGrade(){
  $('unit').innerHTML=units().map(u=>`<option value="${u.unit_id}">${u.unit_name}</option>`).join('');
  onUnit();
}
function currentUnit(){ return units().find(u=>u.unit_id===$('unit').value); }
function onUnit(){
  const u=currentUnit();
  $('kp').innerHTML=u.knowledge_points.map(k=>`<option>${k}</option>`).join('');
  $('type').innerHTML=u.allowed_types.map(t=>`<option value="${t}">${TYPELABEL[t]||t}</option>`).join('');
  const [lo,hi]=u.difficulty_range;
  const opts=[]; for(let d=lo;d<=hi;d++)opts.push(`<option value="${d}">难度 ${d}</option>`);
  $('diff').innerHTML=opts.join('');
}
function answerText(card){
  const a=card.answer||{};
  if('value' in a) return typeof a.value==='boolean'?(a.value?'正确':'错误'):a.value;
  if(Array.isArray(a.values)) return a.values.join('；');
  if(a.text) return a.text;
  return JSON.stringify(a);
}
function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function render(d){
  const out=$('out');
  if(!d.card){
    out.innerHTML=`<div class="status bad">生成失败</div>
      <div class="err">${esc((d.errors||[]).join('\\n')||'无返回')}</div>
      <pre>${esc(d.raw_output||'')}</pre>`; return;
  }
  const c=d.card, ok=d.ok;
  const opts=(c.options||[]).map(o=>`<li class="${o.key===c.answer.value?'right':''}">
      ${esc(o.key)}. ${esc(o.text)}</li>`).join('');
  out.innerHTML=`
    <div class="status ${ok?'ok':'bad'}">${ok?'格式校验通过':'格式校验未通过'}</div>
    ${ok?'':`<div class="err">${esc((d.errors||[]).join('\\n'))}</div>`}
    <div class="tags">
      <span class="tag">${esc(gradeLabel(c.grade))}</span>
      <span class="tag">${esc(c.unit_name)}</span>
      <span class="tag">${esc(c.knowledge_point)}</span>
      <span class="tag">${esc(TYPELABEL[c.type]||c.type)}</span>
      <span class="tag">难度 ${esc(c.difficulty)}</span>
    </div>
    <div class="stem">${esc(c.stem)}</div>
    ${opts?`<ul class="opts">${opts}</ul>`:''}
    <div class="kv"><b>答案</b>${esc(answerText(c))}</div>
    <div class="kv"><b>解析</b>${esc(c.analysis)}</div>
    <details><summary class="muted">原始 JSON</summary><pre>${esc(JSON.stringify(d,null,2))}</pre></details>`;
}
let lastPaper=null,lastTitle='',lastNote='';
function cardHead(c,i){
  return `<div class="tags"><span class="tag">第 ${i+1} 题</span><span class="tag">${esc(TYPELABEL[c.type]||c.type)}</span><span class="tag">${esc(c.unit_name)}</span><span class="tag">${esc(c.knowledge_point)}</span><span class="tag">${c.score} 分</span></div>
    <div class="stem">${esc(c.stem)}</div>`;
}
function renderTeacherCard(c,i){
  const opts=(c.options||[]).map(o=>`<li class="${o.key===c.answer.value?'right':''}">${esc(o.key)}. ${esc(o.text)}</li>`).join('');
  return `<div style="border-top:1px solid var(--line);padding-top:12px;margin-top:12px">${cardHead(c,i)}
    ${opts?`<ul class="opts">${opts}</ul>`:''}
    <div class="kv"><b>答案</b>${esc(answerText(c))}</div>
    <div class="kv"><b>解析</b>${esc(c.analysis)}</div></div>`;
}
function renderStudentCard(c,i){
  let body='';
  if(c.type==='single_choice'){
    body=`<ul class="opts">${(c.options||[]).map(o=>`<li data-key="${esc(o.key)}" onclick="selOpt(this)">${esc(o.key)}. ${esc(o.text)}</li>`).join('')}</ul>`;
  }else if(c.type==='true_false'){
    body=`<div style="display:flex;gap:8px"><button class="tfbtn" data-val="true" onclick="selTF(this)">正确</button><button class="tfbtn" data-val="false" onclick="selTF(this)">错误</button></div>`;
  }else if(c.type==='fill_blank'){
    const n=Math.max(1,(c.stem.match(/_{2,}/g)||[]).length);
    body=`<div style="display:flex;gap:8px;flex-wrap:wrap">${Array.from({length:n},(_,j)=>`<input class="blank" placeholder="第 ${j+1} 空" style="flex:1;min-width:120px">`).join('')}</div>`;
  }else{
    body=`<textarea class="sa" rows="3" placeholder="写下你的答案" style="width:100%;padding:8px;border:1px solid var(--line);border-radius:6px;font-size:14px"></textarea>`;
  }
  return `<div class="qblock" data-qid="${esc(c.id)}" data-qtype="${esc(c.type)}" style="border-top:1px solid var(--line);padding-top:12px;margin-top:12px">${cardHead(c,i)}${body}</div>`;
}
function selOpt(el){const b=el.closest('.qblock');b.querySelectorAll('.opts li').forEach(x=>x.classList.remove('sel'));el.classList.add('sel');}
function selTF(el){const b=el.closest('.qblock');b.querySelectorAll('.tfbtn').forEach(x=>x.classList.remove('sel'));el.classList.add('sel');}
function renderPaper(d,title,note){
  lastPaper=d; lastTitle=title; lastNote=note;
  const student=$('studentMode')&&$('studentMode').checked;
  const short=d.shortfalls&&Object.keys(d.shortfalls).length?`（数量不足：${JSON.stringify(d.shortfalls)}）`:'';
  const head=`<div class="status ok">${esc(title)} · 共 ${d.count} 题 / ${d.total_score} 分${esc(short)}${student?' · 学生答题模式':''}</div>`+(note?`<p class="muted">${esc(note)}</p>`:'');
  const body=student?d.cards.map(renderStudentCard).join(''):d.cards.map(renderTeacherCard).join('');
  $('out').innerHTML=head+body+(student?'<button onclick="submitPaper()" style="margin-top:16px">交卷评分</button>':'');
}
function rerender(){ if(lastPaper) renderPaper(lastPaper,lastTitle,lastNote); }
async function submitPaper(){
  const blocks=[...document.querySelectorAll('.qblock')];
  if(!blocks.length) return;
  const items=blocks.map(b=>{
    const type=b.dataset.qtype; let response=null;
    if(type==='single_choice'){const s=b.querySelector('.opts li.sel');response=s?s.dataset.key:null;}
    else if(type==='true_false'){const s=b.querySelector('.tfbtn.sel');response=s?s.dataset.val==='true':null;}
    else if(type==='fill_blank'){response=[...b.querySelectorAll('.blank')].map(i=>i.value.trim());}
    else{const t=b.querySelector('.sa');response=t?t.value.trim():'';}
    return {id:b.dataset.qid,response};
  });
  $('out').insertAdjacentHTML('beforeend','<p class="muted" id="grading">判分中…</p>');
  try{
    const r=await fetch('/grade',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items})});
    const d=await r.json();
    if(!r.ok){$('grading').outerHTML=`<div class="status bad">判分失败</div><div class="err">${esc(JSON.stringify(d))}</div>`;return;}
    renderResult(d);
  }catch(e){$('grading').outerHTML=`<div class="status bad">判分失败</div><div class="err">${esc(e)}</div>`;}
}
function renderResult(d){
  const head=`<div class="status ok">得分 ${d.earned_score} / ${d.total_score}${d.manual_pending?`（${d.manual_pending} 道解答题待教师评分）`:''}</div>`;
  const body=d.items.map((r,i)=>{
    const mark=r.needs_manual?'<span class="tag" style="background:#fff8c5;color:#9a6700">待教师评分</span>':(r.correct?'<span class="tag" style="background:#dafbe1;color:#1a7f37">正确</span>':'<span class="tag" style="background:#ffebe9;color:#cf222e">错误</span>');
    const mine=r.response==null?'未作答':(Array.isArray(r.response)?r.response.join('、'):(typeof r.response==='boolean'?(r.response?'正确':'错误'):r.response));
    return `<div style="border-top:1px solid var(--line);padding-top:12px;margin-top:12px">
      <div class="tags"><span class="tag">第 ${i+1} 题</span><span class="tag">${esc(TYPELABEL[r.type]||r.type)}</span>${mark}<span class="tag">${r.score}/${r.max_score}</span></div>
      <div class="stem">${esc(r.stem)}</div>
      <div class="kv"><b>你的答案</b>${esc(mine)}</div>
      <div class="kv"><b>正确答案</b>${esc(answerText({answer:r.answer}))}</div>
      <div class="kv"><b>解析</b>${esc(r.analysis)}</div></div>`;
  }).join('');
  $('out').innerHTML=head+body+'<button onclick="rerender()" style="margin-top:16px">重新作答</button>';
}
async function loadDemo(){
  $('out').innerHTML='<p class="muted">加载中…</p>';
  try{
    const url=($('studentMode')&&$('studentMode').checked)?'/demo?with_answer=0':'/demo';
    const r=await fetch(url); const d=await r.json();
    if(!r.ok) throw new Error(JSON.stringify(d));
    renderPaper(d,'演示卷（人工审校版，非模型实时生成）','固定题，不调用模型，可反复点击。');
  }catch(e){ $('out').innerHTML=`<div class="status bad">加载失败</div><div class="err">${esc(e)}</div>`; }
}
async function paperGen(){
  const t0=performance.now();
  $('out').innerHTML='<p class="muted">组卷中…</p>';
  const q=new URLSearchParams({grade:$('grade').value,
    single_choice:$('n_sc').value,true_false:$('n_tf').value,
    fill_blank:$('n_fb').value,short_answer:$('n_sa').value});
  if($('unit').value) q.set('unit_id',$('unit').value);
  if($('studentMode')&&$('studentMode').checked) q.set('with_answer','0');
  try{
    const r=await fetch('/paper?'+q.toString()); const d=await r.json();
    if(!r.ok){$('out').innerHTML=`<div class="status bad">组卷失败 ${r.status}</div><div class="err">${esc(JSON.stringify(d))}</div>`;return;}
    const ms=performance.now()-t0;
    renderPaper(d,`${gradeLabel($('grade').value)} 试卷`,`组卷耗时 ${ms.toFixed(0)} 毫秒。题目来自待审题库，正式使用前需人工复核。`);
    $('hint').textContent=`组卷耗时 ${ms.toFixed(0)} 毫秒`;
  }catch(e){ $('out').innerHTML=`<div class="status bad">组卷失败</div><div class="err">${esc(e)}</div>`; }
}
async function gen(){
  const btn=$('go'); btn.disabled=true; btn.textContent='生成中…';
  $('hint').textContent='正在生成，通常 10 秒左右；首次需加载模型。';
  const body={unit_id:$('unit').value,knowledge_point:$('kp').value,
              type:$('type').value,difficulty:Number($('diff').value)};
  const t0=performance.now();
  try{
    const r=await fetch('/generate',{method:'POST',headers:{'Content-Type':'application/json'},
                                    body:JSON.stringify(body)});
    const d=await r.json();
    if(!r.ok){$('out').innerHTML=`<div class="status bad">请求失败 ${r.status}</div>
      <div class="err">${esc(JSON.stringify(d,null,2))}</div>`;}
    else{render(d); $('hint').textContent=`本次耗时 ${((performance.now()-t0)/1000).toFixed(1)} 秒`;}
  }catch(e){
    $('out').innerHTML=`<div class="status bad">请求失败</div><div class="err">${esc(e)}</div>`;
  }finally{btn.disabled=false;btn.textContent='生成题目';}
}
init();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return TEST_PAGE


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model_loaded": runtime.loaded,
        "model_path": str(runtime.model_path),
        "adapter": str(runtime.adapter_path) if runtime.adapter_path.exists() else None,
    }


@app.get("/catalog")
def catalog() -> dict:
    return runtime.catalog


BANK_PATH = Path(
    os.getenv(
        "QGEN_BANK",
        Path(__file__).resolve().parents[2] / "02_data" / "train_clean_2698.jsonl",
    )
)
DEFAULT_SCORES = {"single_choice": 5, "true_false": 2, "fill_blank": 4, "short_answer": 10}
_bank: list[dict] | None = None


def bank() -> list[dict]:
    global _bank
    if _bank is None:
        if not BANK_PATH.exists():
            raise FileNotFoundError(f"题库文件不存在：{BANK_PATH}")
        with BANK_PATH.open(encoding="utf-8") as fh:
            _bank = [json.loads(line) for line in fh if line.strip()]
    return _bank


DEMO_PATH = Path(
    os.getenv(
        "QGEN_DEMO",
        Path(__file__).resolve().parents[2] / "04_eval" / "demo_papers" / "fixed_demo_grade3.json",
    )
)


@app.get("/demo")
def demo(with_answer: bool = True) -> dict:
    """演示用固定卷：人工逐条确认过，不随机、不调用模型。"""
    if not DEMO_PATH.exists():
        raise HTTPException(status_code=404, detail=f"演示卷不存在：{DEMO_PATH}")
    with DEMO_PATH.open(encoding="utf-8") as fh:
        paper = json.load(fh)
    if not with_answer:
        for card in paper["cards"]:
            card.pop("answer", None)
            card.pop("analysis", None)
    return paper


@app.get("/paper")
def paper(
    grade: int,
    unit_id: str | None = None,
    difficulty: int | None = None,
    single_choice: int = 5,
    true_false: int = 5,
    fill_blank: int = 4,
    short_answer: int = 2,
    with_answer: bool = True,
) -> dict:
    """从交付题库组一套试卷，秒级返回，不调用模型。"""
    if not 1 <= grade <= 9:
        raise HTTPException(status_code=400, detail="grade 必须是 1–9")
    wanted = {
        "single_choice": single_choice,
        "true_false": true_false,
        "fill_blank": fill_blank,
        "short_answer": short_answer,
    }
    if any(count < 0 for count in wanted.values()):
        raise HTTPException(status_code=400, detail="各题型数量不能为负")

    cards = [card for card in bank() if card["grade"] == grade]
    if unit_id:
        cards = [card for card in cards if card["unit_id"] == unit_id]
    if difficulty:
        cards = [card for card in cards if card["difficulty"] == difficulty]
    if not cards:
        raise HTTPException(status_code=404, detail="该范围内没有题卡")

    picked: list[dict] = []
    shortfalls: dict[str, int] = {}
    for qtype, count in wanted.items():
        pool = [card for card in cards if card["type"] == qtype]
        random.shuffle(pool)
        taken = pool[:count]
        if len(taken) < count:
            shortfalls[qtype] = count - len(taken)
        for card in taken:
            item = dict(card)
            item["score"] = DEFAULT_SCORES[qtype]
            item["review_status"] = item.get("review_status", "pending")
            if not with_answer:
                item.pop("answer", None)
                item.pop("analysis", None)
            picked.append(item)

    for number, item in enumerate(picked, 1):
        item["question_no"] = number
    return {
        "grade": grade,
        "unit_id": unit_id,
        "difficulty": difficulty,
        "count": len(picked),
        "total_score": sum(item["score"] for item in picked),
        "shortfalls": shortfalls,
        "source": str(BANK_PATH),
        "notice": "题目来自待审题库，入库或用于正式测评前必须人工复核。",
        "cards": picked,
    }


class GradeItem(BaseModel):
    id: str
    response: Any = None


class GradeRequest(BaseModel):
    items: list[GradeItem]


def _norm_answer(text: Any) -> str:
    return re.sub(r"[\s\W_]+", "", str(text)).lower()


@app.post("/grade")
def grade(payload: GradeRequest) -> dict:
    """学生提交后判分；答案与解析只在这里返回，组卷接口不返回。"""
    index = {card["id"]: card for card in bank()}
    results: list[dict] = []
    total = 0.0
    earned = 0.0
    manual = 0
    for item in payload.items:
        card = index.get(item.id)
        if card is None:
            raise HTTPException(status_code=404, detail=f"题卡不存在：{item.id}")
        max_score = float(card.get("score", 0))
        total += max_score
        correct: bool | None = None
        response = item.response

        if card["type"] == "single_choice":
            correct = str(response or "").strip().upper() == str(card["answer"]["value"]).upper()
        elif card["type"] == "true_false":
            if isinstance(response, bool):
                correct = response == card["answer"]["value"]
            else:
                text = str(response or "").strip().lower()
                correct = (
                    (text in {"true", "正确", "对", "是"} and card["answer"]["value"] is True)
                    or (text in {"false", "错误", "错", "否"} and card["answer"]["value"] is False)
                )
            if correct is None:
                correct = False
        elif card["type"] == "fill_blank":
            expected = [str(v) for v in card["answer"].get("values", [])]
            given = response if isinstance(response, list) else [response]
            correct = bool(expected) and len(given) == len(expected) and all(
                _norm_answer(g) and _norm_answer(g) == _norm_answer(e)
                for g, e in zip(given, expected)
            )
        else:
            manual += 1

        score = max_score if correct else 0.0
        earned += score
        results.append(
            {
                "id": card["id"],
                "question_no": len(results) + 1,
                "type": card["type"],
                "stem": card["stem"],
                "response": response,
                "correct": correct,
                "score": score,
                "max_score": max_score,
                "answer": card["answer"],
                "analysis": card["analysis"],
                "needs_manual": correct is None,
            }
        )

    return {
        "count": len(results),
        "total_score": total,
        "earned_score": round(earned, 1),
        "manual_pending": manual,
        "items": results,
    }


@app.post("/generate")
def generate(payload: GenerateRequest) -> dict:
    try:
        record = runtime.generate(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    record["ok"] = record["parse_ok"] and not record["errors"]
    return record

"""出题测试页：FastAPI 根路由返回的交互页面。"""

TEST_PAGE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>模型B · 出题测试台</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{
  --bg:#eef1f6;--panel:#fff;--ink:#0f172a;--dim:#64748b;--line:#e2e8f0;
  --accent:#2563eb;--accent-2:#4f46e5;--ok:#0f766e;--okbg:#ecfdf5;
  --bad:#b91c1c;--badbg:#fef2f2;--warn:#b45309;--warnbg:#fffbeb;
  --shadow:0 10px 30px rgba(15,23,42,.07);
}
*{box-sizing:border-box}
html,body{margin:0}
body{min-height:100vh;background:
  radial-gradient(1100px 500px at 85% -10%,#dbeafe 0%,transparent 60%),
  radial-gradient(900px 500px at -10% 10%,#ede9fe 0%,transparent 55%),
  var(--bg);
  color:var(--ink);font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:16px;
  padding:18px 32px;background:linear-gradient(120deg,#0f172a 0%,#1e3a8a 58%,#1d4ed8 100%);
  color:#fff;box-shadow:0 6px 24px rgba(15,23,42,.18)}
.brand{display:flex;align-items:center;gap:14px}
.logo{width:44px;height:44px;border-radius:12px;background:rgba(255,255,255,.14);
  border:1px solid rgba(255,255,255,.25);display:grid;place-items:center;
  font-size:20px;font-weight:800;letter-spacing:.5px}
.brand h1{margin:0;font-size:19px;letter-spacing:.3px}
.brand p{margin:2px 0 0;font-size:12px;color:#bfdbfe}
.health{font-size:12px;padding:6px 12px;border-radius:999px;white-space:nowrap;
  background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.22);color:#e0e7ff}
.health.ok{background:rgba(16,185,129,.18);border-color:rgba(52,211,153,.5);color:#a7f3d0}
.health.bad{background:rgba(239,68,68,.18);border-color:rgba(248,113,113,.5);color:#fecaca}
.wrap{max-width:1200px;margin:0 auto;padding:24px 32px 48px;display:grid;
  grid-template-columns:370px minmax(0,1fr);gap:22px;align-items:start}
@media(max-width:920px){.wrap{grid-template-columns:1fr}.topbar{padding:16px 18px}}
.panel,.result{background:var(--panel);border:1px solid var(--line);border-radius:16px;
  box-shadow:var(--shadow)}
.panel{padding:20px}
.section-title{display:flex;align-items:center;justify-content:space-between;
  font-size:13px;font-weight:700;color:#334155;letter-spacing:.4px;margin:0 0 12px}
.section-title .hint{font-weight:500;color:var(--dim);font-size:11.5px}
.divider{height:1px;background:var(--line);margin:18px 0}
label{display:block;font-size:12px;color:var(--dim);margin:11px 0 5px}
select,input{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:9px;
  background:#fbfcfe;font-size:13.5px;color:var(--ink);outline:none;transition:.15s}
select:focus,input:focus{border-color:#93c5fd;background:#fff;box-shadow:0 0 0 3px rgba(37,99,235,.12)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px 10px;margin-top:4px}
.grid2 .field label{margin:0 0 4px;font-size:11.5px}
.btn{width:100%;margin-top:14px;padding:10px 14px;border-radius:10px;cursor:pointer;
  font-size:14px;font-weight:600;border:1px solid transparent;transition:.18s}
.btn:disabled{opacity:.6;cursor:wait}
.btn.primary{background:linear-gradient(135deg,var(--accent),var(--accent-2));color:#fff;
  box-shadow:0 6px 16px rgba(37,99,235,.3)}
.btn.primary:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 9px 20px rgba(37,99,235,.36)}
.btn.ghost{background:#fff;border-color:#bfdbfe;color:#1d4ed8}
.btn.ghost:hover{background:#eff6ff}
.btn.green{background:#ecfdf5;border-color:#a7f3d0;color:#047857}
.btn.green:hover{background:#d1fae5}
.btn.solid-green{background:linear-gradient(135deg,#059669,#047857);color:#fff;
  border-color:transparent;box-shadow:0 6px 16px rgba(5,150,105,.25)}
.switch-row{display:flex;align-items:center;gap:9px;margin-top:14px;font-size:12.5px;color:#334155}
.switch-row input{width:auto;margin:0;accent-color:var(--accent)}
.hint-text{color:var(--dim);font-size:12px;margin:12px 0 0;line-height:1.6}
.result{padding:22px;min-height:520px}
.empty{min-height:470px;display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:10px;color:var(--dim);border:1.5px dashed #dbe2ea;
  border-radius:14px;background:linear-gradient(180deg,#fbfcfe,#f6f8fc)}
.empty .art{width:58px;height:58px;border-radius:16px;background:#eef2ff;color:#4f46e5;
  display:grid;place-items:center;font-size:24px;font-weight:700}
.empty b{color:#334155;font-size:15px}
.empty span{font-size:12.5px;max-width:320px;text-align:center}
.status{display:inline-flex;align-items:center;gap:7px;font-weight:600;font-size:13px;
  padding:5px 12px;border-radius:999px;margin-bottom:14px}
.status.ok{background:var(--okbg);color:var(--ok)}
.status.bad{background:var(--badbg);color:var(--bad)}
.status::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.tags{display:flex;gap:7px;flex-wrap:wrap;margin:4px 0 14px}
.tag{font-size:11.5px;background:#eff6ff;color:#1d4ed8;border-radius:999px;padding:3px 10px;
  border:1px solid #dbeafe}
.tag.gray{background:#f1f5f9;color:#475569;border-color:#e2e8f0}
.stem{font-size:16.5px;line-height:1.75;margin:6px 0 16px;color:#111827}
.qimg{display:block;max-width:100%;max-height:340px;margin:10px 0 14px;border:1px solid var(--line);border-radius:10px;background:#fafafa;object-fit:contain}
.opts{list-style:none;padding:0;margin:0 0 16px;display:grid;gap:8px}
.opts li{padding:10px 13px;border:1px solid var(--line);border-radius:10px;background:#fbfcfe;
  cursor:pointer;transition:.14s;font-size:14px}
.opts li:hover{border-color:#bfdbfe;background:#f8fbff}
.opts li.sel{border-color:var(--accent);background:#eff6ff;box-shadow:0 0 0 3px rgba(37,99,235,.1)}
.opts li.right{border-color:#34d399;background:#ecfdf5}
.kv{margin:10px 0;padding:12px 14px;border-radius:10px;background:#f8fafc;border:1px solid #eef2f7}
.kv b{display:block;font-size:11.5px;color:var(--dim);font-weight:600;letter-spacing:.3px;margin-bottom:3px}
.err{background:var(--badbg);border:1px solid #fecaca;border-radius:10px;padding:12px 14px;
  margin-bottom:12px;color:var(--bad);font-size:13px;white-space:pre-wrap}
pre{background:#0f172a;color:#e2e8f0;border-radius:10px;padding:12px 14px;font-size:12px;
  overflow:auto;max-height:360px;white-space:pre-wrap;line-height:1.6}
details{margin-top:12px}
details summary{cursor:pointer;color:var(--dim);font-size:12.5px;user-select:none}
button.tfbtn{width:auto;min-width:96px;padding:9px 22px;border-radius:10px;border:1px solid var(--line);
  background:#fff;font-size:14px;cursor:pointer;margin-right:8px;color:#334155}
button.tfbtn.sel{background:var(--accent);border-color:var(--accent);color:#fff}
.qblock{border-top:1px solid var(--line);padding-top:16px;margin-top:16px}
.qblock:first-of-type{border-top:0;padding-top:0;margin-top:0}
.scoreread{display:inline-block;font-size:26px;font-weight:800;color:#0f766e;margin-right:8px}
.muted{color:var(--dim);font-size:13px}
.spin{display:inline-block;width:14px;height:14px;border:2px solid rgba(255,255,255,.45);
  border-top-color:#fff;border-radius:50%;animation:sp .7s linear infinite;margin-right:7px;
  vertical-align:-2px}
@keyframes sp{to{transform:rotate(360deg)}}
</style></head><body>
<div class="topbar">
  <div class="brand">
    <div class="logo">B</div>
    <div>
      <h1>模型B · 出题测试台</h1>
      <p>Qwen2.5-3B + LoRA v4 · 知识卡锚定 · 自动重试 · 约 10 秒/题</p>
    </div>
  </div>
  <div class="health" id="health">检测服务中…</div>
</div>
<div class="wrap">
  <div class="panel">
    <div class="section-title">实时出题 <span class="hint">格式校验通过 ≠ 内容正确</span></div>
    <label>年级</label><select id="grade"></select>
    <label>单元</label><select id="unit"></select>
    <label>知识点</label><select id="kp"></select>
    <label>题型</label><select id="type"></select>
    <label>难度</label><select id="diff"></select>
    <label class="switch-row">
      <input type="checkbox" id="withImage" checked>
      生成图像题（该知识点有图题素材时返回带图的题）
    </label>
    <button class="btn primary" id="go" onclick="gen()">生成题目</button>

    <div class="divider"></div>
    <div class="section-title">快速组卷 <span class="hint">从题库抽取 · 毫秒级</span></div>
    <div class="grid2">
      <div class="field"><label>选择题</label><input id="n_sc" type="number" value="5" min="0" max="20"></div>
      <div class="field"><label>判断题</label><input id="n_tf" type="number" value="5" min="0" max="20"></div>
      <div class="field"><label>填空题</label><input id="n_fb" type="number" value="4" min="0" max="20"></div>
      <div class="field"><label>解答题</label><input id="n_sa" type="number" value="2" min="0" max="20"></div>
    </div>
    <button class="btn ghost" onclick="paperGen()">快速组卷</button>
    <button class="btn solid-green" id="goBatch" onclick="genBatch()">实时生成整套（含图题）</button>
    <button class="btn green" onclick="loadDemo()">加载固定演示卷</button>

    <label class="switch-row">
      <input type="checkbox" id="studentMode" onchange="rerender()">
      学生答题模式（不返回答案，交卷后判分）
    </label>
    <p class="hint-text" id="hint">首次生成需要加载模型，可能多等 1–2 分钟。</p>
  </div>
  <div class="result" id="out">
    <div class="empty">
      <div class="art">B</div>
      <b>结果会显示在这里</b>
      <span>左侧选择年级、单元、知识点后点「生成题目」，或直接快速组卷 / 加载演示卷。</span>
    </div>
  </div>
</div>
<script>
const $=id=>document.getElementById(id);
let CAT=null, IMGCOV=new Set();
const TYPELABEL={single_choice:'选择',multiple_choice:'多选',true_false:'判断',fill_blank:'填空',short_answer:'解答'};
const GRADELABEL={'1':'小学一年级','2':'小学二年级','3':'小学三年级','4':'小学四年级','5':'小学五年级','6':'小学六年级','7':'初中一年级','8':'初中二年级','9':'初中三年级'};
const gradeLabel=g=>GRADELABEL[g]||`${g} 年级`;
async function checkHealth(){
  const el=$('health');
  try{
    const r=await fetch('/health'); const d=await r.json();
    if(d.status==='ok'){
      el.className='health ok';
      el.textContent=d.model_loaded?'服务正常 · 模型已加载':'服务正常 · 模型待加载';
    }else{el.className='health bad';el.textContent='服务异常';}
  }catch(e){ el.className='health bad'; el.textContent='服务未连接'; }
}
async function init(){
  checkHealth();
  try{
    const r=await fetch('/catalog'); CAT=await r.json();
    const c=await fetch('/image_coverage');
    if(c.ok){
      const cov=await c.json();
      IMGCOV=new Set((cov.items||[]).map(x=>x.slice(1).join('|')));
    }
  }catch(e){
    $('out').innerHTML=`<div class="status bad">目录加载失败</div><div class="err">${esc(e)}</div>`;return;
  }
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
function tags(c,extra){
  return `<div class="tags">
    ${extra||''}
    <span class="tag">${esc(gradeLabel(c.grade))}</span>
    <span class="tag">${esc(c.unit_name)}</span>
    <span class="tag gray">${esc(c.knowledge_point)}</span>
    <span class="tag">${esc(TYPELABEL[c.type]||c.type)}</span>
    <span class="tag gray">难度 ${esc(c.difficulty)}</span>
  </div>`;
}
function render(d){
  const out=$('out');
  if(!d.card){
    out.innerHTML=`<div class="status bad">生成失败</div>
      <div class="err">${esc((d.errors||[]).join('\\n')||'无返回')}</div>
      <pre>${esc(d.raw_output||'')}</pre>`; return;
  }
  const c=d.card, ok=d.ok;
  const image=(d.resources||[]).find(x=>x&&x.url&&x.role!=='reference');
  const opts=(c.options||[]).map(o=>`<li class="${o.key===c.answer.value?'right':''}">
      ${esc(o.key)}. ${esc(o.text)}</li>`).join('');
  out.innerHTML=`
    <div class="status ${ok?'ok':'bad'}">${ok?'格式校验通过':'格式校验未通过'}</div>
    ${ok?'':`<div class="err">${esc((d.errors||[]).join('\\n'))}</div>`}
    ${tags(c)}
    ${image?`<img class="qimg" src="${esc(image.url)}" alt="${esc(image.name||'')}">`:''}
    <div class="stem">${esc(c.stem)}</div>
    ${opts?`<ul class="opts">${opts}</ul>`:''}
    <div class="kv"><b>答案</b>${esc(answerText(c))}</div>
    <div class="kv"><b>解析</b>${esc(c.analysis)}</div>
    <details><summary>查看原始 JSON</summary><pre>${esc(JSON.stringify(d,null,2))}</pre></details>`;
}
let lastPaper=null,lastTitle='',lastNote='';
function cardHead(c,i){
  return `<div class="tags"><span class="tag">第 ${i+1} 题</span><span class="tag">${esc(TYPELABEL[c.type]||c.type)}</span><span class="tag gray">${esc(c.unit_name)}</span><span class="tag gray">${esc(c.knowledge_point)}</span><span class="tag gray">${c.score} 分</span></div>
    <div class="stem">${esc(c.stem)}</div>`;
}
function cardImage(c){
  const img=(c.resources||[]).find(x=>x&&x.url&&x.role!=='reference');
  return img?`<img class="qimg" src="${esc(img.url)}" alt="${esc(img.name||'')}">`:'';
}
function renderTeacherCard(c,i){
  const opts=(c.options||[]).map(o=>`<li class="${o.key===c.answer.value?'right':''}">${esc(o.key)}. ${esc(o.text)}</li>`).join('');
  return `<div class="qblock">${cardHead(c,i)}${cardImage(c)}
    ${opts?`<ul class="opts">${opts}</ul>`:''}
    <div class="kv"><b>答案</b>${esc(answerText(c))}</div>
    <div class="kv"><b>解析</b>${esc(c.analysis)}</div></div>`;
}
function renderStudentCard(c,i){
  let body='';
  if(c.type==='single_choice'){
    body=`<ul class="opts">${(c.options||[]).map(o=>`<li data-key="${esc(o.key)}" onclick="selOpt(this)">${esc(o.key)}. ${esc(o.text)}</li>`).join('')}</ul>`;
  }else if(c.type==='true_false'){
    body=`<div style="display:flex;gap:8px;margin-bottom:12px"><button class="tfbtn" data-val="true" onclick="selTF(this)">正确</button><button class="tfbtn" data-val="false" onclick="selTF(this)">错误</button></div>`;
  }else if(c.type==='fill_blank'){
    const n=Math.max(1,(c.stem.match(/_{2,}/g)||[]).length);
    body=`<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">${Array.from({length:n},(_,j)=>`<input class="blank" placeholder="第 ${j+1} 空" style="flex:1;min-width:120px">`).join('')}</div>`;
  }else{
    body=`<textarea class="sa" rows="3" placeholder="写下你的答案" style="width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:9px;font-size:14px;background:#fbfcfe;outline:none"></textarea>`;
  }
  return `<div class="qblock" data-qid="${esc(c.id)}" data-qtype="${esc(c.type)}">${cardHead(c,i)}${cardImage(c)}${body}</div>`;
}
function selOpt(el){const b=el.closest('.qblock');b.querySelectorAll('.opts li').forEach(x=>x.classList.remove('sel'));el.classList.add('sel');}
function selTF(el){const b=el.closest('.qblock');b.querySelectorAll('.tfbtn').forEach(x=>x.classList.remove('sel'));el.classList.add('sel');}
function renderPaper(d,title,note,opts){
  lastPaper=d; lastTitle=title; lastNote=note;
  const student=!(opts&&opts.teacher)&&$('studentMode')&&$('studentMode').checked;
  const short=d.shortfalls&&Object.keys(d.shortfalls).length?`（数量不足：${JSON.stringify(d.shortfalls)}）`:'';
  const head=`<div class="status ok">${esc(title)} · 共 ${d.count} 题 / ${d.total_score} 分${esc(short)}${student?' · 学生答题模式':''}</div>`+(note?`<p class="muted">${esc(note)}</p>`:'');
  const body=student?d.cards.map(renderStudentCard).join(''):d.cards.map(renderTeacherCard).join('');
  $('out').innerHTML=head+body+(student?'<button class="btn primary" onclick="submitPaper()" style="margin-top:18px">交卷评分</button>':'');
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
  const head=`<div class="status ok">交卷得分 <span class="scoreread">${d.earned_score}</span> / ${d.total_score}${d.manual_pending?` · ${d.manual_pending} 道解答题待教师评分`:''}</div>`;
  const body=d.items.map((r,i)=>{
    const mark=r.needs_manual?'<span class="tag" style="background:#fffbeb;color:#b45309;border-color:#fde68a">待教师评分</span>':(r.correct?'<span class="tag" style="background:#ecfdf5;color:#047857;border-color:#a7f3d0">正确</span>':'<span class="tag" style="background:#fef2f2;color:#b91c1c;border-color:#fecaca">错误</span>');
    const mine=r.response==null?'未作答':(Array.isArray(r.response)?r.response.join('、'):(typeof r.response==='boolean'?(r.response?'正确':'错误'):r.response));
    return `<div class="qblock">
      <div class="tags"><span class="tag">第 ${i+1} 题</span><span class="tag gray">${esc(TYPELABEL[r.type]||r.type)}</span>${mark}<span class="tag gray">${r.score}/${r.max_score}</span></div>
      <div class="stem">${esc(r.stem)}</div>
      <div class="kv"><b>你的答案</b>${esc(mine)}</div>
      <div class="kv"><b>正确答案</b>${esc(answerText({answer:r.answer}))}</div>
      <div class="kv"><b>解析</b>${esc(r.analysis)}</div></div>`;
  }).join('');
  $('out').innerHTML=head+body+'<button class="btn ghost" onclick="rerender()" style="margin-top:18px">重新作答</button>';
}
async function loadDemo(){
  $('out').innerHTML='<p class="muted">加载中…</p>';
  try{
    const url=($('studentMode')&&$('studentMode').checked)?'/demo?with_answer=0':'/demo';
    const r=await fetch(url); const d=await r.json();
    if(!r.ok) throw new Error(JSON.stringify(d));
    renderPaper(d,'固定演示卷（非模型实时生成）','固定题，不调用模型，可反复点击；题目来自待审题库。');
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
async function genBatch(){
  const btn=$('goBatch'); btn.disabled=true; btn.innerHTML='<span class="spin"></span>生成中…';
  const grade=Number($('grade').value);
  const gradeUnits=CAT.grades[$('grade').value].units;
  const wanted={single_choice:+$('n_sc').value,true_false:+$('n_tf').value,
                fill_blank:+$('n_fb').value,short_answer:+$('n_sa').value};
  const wantImg=$('withImage')?$('withImage').checked:true;
  const reqs=[],missing=[];
  for(const [type,want] of Object.entries(wanted)){
    if(want<=0) continue;
    const pool=[];
    for(const u of gradeUnits){
      if(!(u.allowed_types||[]).includes(type)) continue;
      const [lo,hi]=u.difficulty_range;
      for(const kp of u.knowledge_points)
        pool.push({unit_id:u.unit_id,knowledge_point:kp,range:[lo,hi],
                   img:IMGCOV.has(`${u.unit_id}|${kp}|${type}`)});
    }
    if(!pool.length){ missing.push(type); continue; }
    // 有图素材的知识点优先，保证整套里能看到图题；不足的部分再随机补
    const withImg=pool.filter(p=>p.img).sort(()=>Math.random()-0.5);
    const noImg=pool.filter(p=>!p.img).sort(()=>Math.random()-0.5);
    const pick=withImg.concat(noImg);
    for(let i=0;i<want;i++){
      const p=pick[i%pick.length], [lo,hi]=p.range;
      reqs.push({unit_id:p.unit_id,knowledge_point:p.knowledge_point,type,
                 difficulty:lo+Math.floor(Math.random()*(hi-lo+1)),
                 with_image:wantImg,request_id:`ui-${Date.now()}-${reqs.length}`});
    }
  }
  if(!reqs.length){
    $('out').innerHTML='<div class="status bad">没有可生成的题型，请调整题量</div>';
    btn.disabled=false; btn.textContent='实时生成整套（含图题）'; return;
  }
  const t0=performance.now();
  $('out').innerHTML='<p class="muted">正在生成整套，文字题每题约 10 秒，请稍候…</p>';
  try{
    const r=await fetch('/generate_batch',{method:'POST',headers:{'Content-Type':'application/json'},
                                          body:JSON.stringify({requests:reqs})});
    const d=await r.json();
    if(!r.ok){$('out').innerHTML=`<div class="status bad">生成失败 ${r.status}</div><div class="err">${esc(JSON.stringify(d,null,2))}</div>`;return;}
    const cards=d.items.filter(x=>x.card).map(x=>{
      const c=x.card; c.resources=(x.resources||[]).filter(z=>z&&z.role!=='reference'); return c;});
    const img=cards.filter(c=>(c.resources||[]).length).length;
    const secs=((performance.now()-t0)/1000).toFixed(1);
    const note=`耗时 ${secs} 秒 · 成功 ${cards.length}/${d.count} · 图题 ${img} 道`+
      (missing.length?` · 该年级无 ${missing.map(t=>TYPELABEL[t]||t).join('/')} 题`:'')+
      ' · 实时题不在题库内，暂不支持交卷判分；答案与解析已显示。';
    renderPaper({grade:grade,count:cards.length,
                 total_score:cards.reduce((s,c)=>s+(Number(c.score)||0),0),
                 shortfalls:{},cards:cards},
                `${gradeLabel(grade)} 实时生成整套`,note,{teacher:true});
    $('hint').textContent=`整套耗时 ${secs} 秒`;
  }catch(e){ $('out').innerHTML=`<div class="status bad">生成失败</div><div class="err">${esc(e)}</div>`; }
  finally{ btn.disabled=false; btn.textContent='实时生成整套（含图题）'; checkHealth(); }
}
async function gen(){
  const btn=$('go'); btn.disabled=true; btn.innerHTML='<span class="spin"></span>生成中…';
  $('hint').textContent='正在生成，通常 10 秒左右；首次需加载模型。';
  const body={unit_id:$('unit').value,knowledge_point:$('kp').value,
              type:$('type').value,difficulty:Number($('diff').value),
              with_image: $('withImage') ? $('withImage').checked : true};
  const t0=performance.now();
  try{
    const r=await fetch('/generate',{method:'POST',headers:{'Content-Type':'application/json'},
                                    body:JSON.stringify(body)});
    const d=await r.json();
    if(!r.ok){$('out').innerHTML=`<div class="status bad">请求失败 ${r.status}</div>
      <div class="err">${esc(JSON.stringify(d,null,2))}</div>`;}
    else{render(d); $('hint').textContent=`本次耗时 ${((performance.now()-t0)/1000).toFixed(1)} 秒`; checkHealth();}
  }catch(e){
    $('out').innerHTML=`<div class="status bad">请求失败</div><div class="err">${esc(e)}</div>`;
  }finally{btn.disabled=false;btn.textContent='生成题目';}
}
init();
if(new URLSearchParams(location.search).get('demo')==='1') loadDemo();
</script></body></html>"""

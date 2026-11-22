from __future__ import annotations

import json
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import credentials, oecd, team
from .config import DB_PATH
from .llm import resolve_model, set_activity
from .model_catalog import list_models
from .pipeline import run_pipeline
from .sources import search_all

TASKS: dict[str, dict] = {}
LOCK = threading.Lock()

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>题眼 LitRadar</title>
<style>
:root{--ink:#14181d;--sub:#5b6672;--line:#dfe4ea;--bg:#f6f7f9;--accent:#1f6f5c;--warn:#a4552a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 60px}
header{display:flex;align-items:baseline;gap:12px;border-bottom:2px solid var(--ink);padding-bottom:12px;margin-bottom:22px}
h1{font-size:26px;margin:0;letter-spacing:1px}
.tag{color:var(--sub);font-size:13px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.field{display:flex;flex-direction:column;gap:6px}
.field select{width:100%;max-width:100%;min-width:0}
.field.full{grid-column:1/-1}
.field.span2{grid-column:span 2}
.range{display:flex;align-items:center;gap:10px}
.range input[type=date]{flex:1 1 0;min-width:0}
.range .dash{color:var(--sub);flex:none}
@media (max-width:760px){.grid{grid-template-columns:repeat(2,1fr)}.field.span2,.field.full{grid-column:1/-1}}
@media (max-width:520px){.grid{grid-template-columns:1fr}}
label{font-size:13px;color:var(--sub)}
input,select,textarea{font:inherit;padding:9px 11px;border:1px solid var(--line);background:#fff;border-radius:6px;color:var(--ink)}
textarea{min-height:76px;resize:vertical}
button{font:inherit;padding:11px 26px;border:0;border-radius:6px;background:var(--ink);color:#fff;cursor:pointer}
button:disabled{opacity:.45;cursor:not-allowed}
.actions{display:flex;gap:12px;align-items:center;margin-top:20px}
.hint{color:var(--sub);font-size:13px}
.panel{margin-top:26px;background:#fff;border:1px solid var(--line);border-radius:8px;padding:20px}
.bar{height:6px;background:#e8ebef;border-radius:4px;overflow:hidden}
.bar>i{display:block;height:100%;width:0;background:var(--accent);transition:width .3s}
.log{margin-top:10px;max-height:200px;overflow:auto;background:#f7f8fa;border:1px solid var(--line);border-radius:6px;padding:9px 11px;font:12px/1.65 "Cascadia Mono",Consolas,monospace;color:#3d4650;white-space:pre-wrap;word-break:break-all}
.log:empty{display:none}
.log .hit{color:var(--warn)}
.live{margin-top:8px;font-size:12px;color:var(--sub)}
.step{display:flex;justify-content:space-between;margin-top:10px;font-size:13px;color:var(--sub)}
.tabs{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 14px}
.tabs button{padding:7px 14px;background:#eef1f4;color:var(--ink);font-size:13px}
.tabs button.on{background:var(--ink);color:#fff}
.md{font-size:14px}
.md h2{font-size:19px;margin:22px 0 10px}
.md h3{font-size:15px;margin:16px 0 6px}
.md ul{margin:6px 0 6px 18px;padding:0}
.md li{margin:3px 0}
.md table{border-collapse:collapse;width:100%;font-size:13px;margin:10px 0}
.md th,.md td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
.md th{background:#f0f2f5}
.err{color:var(--warn);white-space:pre-wrap}
.sect{font-size:15px;margin:0 0 8px;padding-left:9px;border-left:3px solid var(--accent)}
.src{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px dashed var(--line);flex-wrap:wrap}
.src input[type=checkbox]{width:16px;height:16px}
.src .name{min-width:150px;font-weight:600}
.badge{font-size:12px;padding:1px 8px;border-radius:10px;border:1px solid var(--line);color:var(--sub)}
.badge.ok{color:var(--accent);border-color:var(--accent)}
.badge.bad{color:var(--warn);border-color:var(--warn)}
.mini{padding:5px 12px;font-size:12px;background:#eef1f4;color:var(--ink)}
.ghost{background:#fff;color:var(--sub);border:1px solid var(--line)}
.cred{margin-top:12px;padding-top:12px;border-top:1px solid var(--line)}
.credhead{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.dim{border:1px solid var(--line);border-radius:6px;padding:10px 12px;margin-bottom:9px;background:#fbfbfc}
.dim .top{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}
.dim .top b{font-size:13px}
.dim .top span{font-size:12px;color:var(--sub)}
.dim select{width:100%;margin-top:6px}
.dim .crit{margin-top:5px;font-size:12px;color:var(--sub)}
.foot{margin-top:34px;color:var(--sub);font-size:12px}
</style>
</head>
<body>
<div class="wrap">
<header><h1>题眼 LitRadar</h1><span class="tag">一个方向进去，一套能开题的证据包出来</span></header>

<div class="panel">
<div class="grid">
  <div class="field full">
    <label>研究方向（必填，一句话）</label>
    <textarea id="direction" placeholder="例：忆阻器类脑神经网络（材料）；根际微生物组与连作障碍（农学）"></textarea>
  </div>
  <div class="field"><label>学科判定</label><select id="domain">
    <option value="auto">自动判定</option><option value="materials">材料与器件</option>
    <option value="agri">植物—微生物/农学</option><option value="biomed">生物医学</option>
    <option value="general">通用</option></select></div>
  <div class="field"><label>OECD 大类</label><select id="oecd_major"><option value="">不指定</option></select></div>
  <div class="field"><label>OECD 子类（Frascati 2007）</label><select id="oecd_sub"><option value="">不指定</option></select></div>
  <div class="field span2"><label>年份范围（起 — 止）</label>
    <div class="range">
      <input id="year_from" type="date" value="2015-01-01" min="1900-01-01" max="2100-12-31">
      <span class="dash">—</span>
      <input id="year_to" type="date" value="2026-12-31" min="1900-01-01" max="2100-12-31">
    </div></div>
  <div class="field"><label>检索上限（篇）</label><input id="search" type="number" value="40" min="5" max="200"></div>
  <div class="field"><label>精读上限（篇）</label><input id="fetch" type="number" value="8" min="1" max="30"></div>
  <div class="field"><label>卡片上限（篇）</label><input id="cards" type="number" value="8" min="1" max="30"></div>
  <div class="field span2"><label>申请人（写在开题报告封面）</label><input id="owner" placeholder="姓名，可留空"></div>
  <div class="field"><label>模型（读取自 DSH）</label><select id="model"><option value="">正在读取 DSH 模型…</option></select></div>
</div>
<div class="actions"><button id="run">开始分析</button><span class="hint">全程自动跑：检索 → 抓全文 → 抽卡片 → 聚合 → 出简报</span></div>
</div>

<div class="panel">
<h2 class="sect">检索源与账号</h2>
<p class="hint">WOS / Scopus 走机构订阅的 API Key，插件不保存账号密码；Key 存在本机用户目录，过期自动停用。</p>
<div id="sources"></div>
<div id="credform" class="cred" style="display:none">
  <div class="credhead"><b id="credtitle"></b><button class="mini" id="credclose">收起</button></div>
  <div id="credfields" class="grid"></div>
  <div class="actions"><button id="credsave">保存到本机</button><button class="ghost" id="credtest">测试连接</button><button class="ghost" id="credclear">清除</button><span class="hint" id="credmsg"></span></div>
</div>
</div>

<div class="panel">
<h2 class="sect">课题组条件（基金评审五维 + 研究条件）</h2>
<p class="hint">先填单位、通讯作者、人数、在研项目这些能核对的事实，插件按规则推算五维等级；要精确可逐项改下拉。不再用滑杆自评。</p>
<div class="grid" id="teamquick"></div>
<div class="actions">
  <button class="mini" id="teamderive">按填写重新推算</button>
  <button class="mini" id="teamsave">保存</button>
  <span class="hint" id="teamhint">五维默认随填写自动更新</span>
</div>
<div id="teamdims" style="margin-top:14px"></div>
<h3 class="sect" style="margin-top:16px">研究条件</h3>
<p class="hint">原来单独放在首页的实验类型、经费、周期、湿实验，并到这里——它们本来就属于“接不接得住”，不属于方向本身。</p>
<div class="grid" id="teamcond"></div>
<div class="actions"><span class="hint" id="teamscore"></span></div>
</div>

<div class="panel" id="progress" style="display:none">
  <div class="bar"><i id="fill"></i></div>
  <div class="step"><span id="step">准备中</span><span id="pct">0%</span></div>
  <div class="hint" id="detail" style="margin-top:8px"></div>
  <div class="live" id="live"></div>
  <div class="log" id="log"></div>
  <div class="err" id="error"></div>
</div>

<div class="panel" id="result" style="display:none">
  <div class="step"><span id="meta"></span>
    <span><a id="dlreport" href="#" style="color:var(--accent)">证据简报.md</a>
    <a id="dlproposal" href="#" style="color:var(--accent);margin-left:12px">开题报告.md</a>
    <a id="dldocx" href="#" style="color:var(--accent);margin-left:12px">开题报告.docx</a></span></div>
  <div class="tabs" id="tabs"></div>
  <div class="md" id="md"></div>
</div>

<div class="foot">结论均要求原文引句定位；标“待核”表示未找到可核对证据。只抓开放获取文献，不绕过付费墙。</div>
</div>

<script>
let taskId=null,timer=null;
const $=id=>document.getElementById(id);
let CRED=null, DIMS=[], SCHEMA=null, TEAM=null;
function loadSettings(){
  fetch("/api/settings").then(r=>r.json()).then(d=>{
    buildOecd(d.oecd||[]);
    renderSources(d.sources||[]);
    SCHEMA=d.team.schema||{identity:[],dimensions:[],conditions:[]};
    DIMS=SCHEMA.dimensions||[];
    TEAM=d.team.profile||{identity:{},dims:{},conditions:{}};
    renderTeam();
  }).catch(e=>{$("sources").textContent="读取配置失败："+e;});
}
function buildOecd(rows){
  const major=$("oecd_major");major.innerHTML='<option value="">不指定</option>';
  rows.forEach(m=>{const o=document.createElement("option");o.value=m.code;o.textContent=m.label;major.appendChild(o);});
  major.onchange=()=>{
    const sub=$("oecd_sub");sub.innerHTML='<option value="">不指定（按方向自动判定）</option>';
    const row=rows.find(m=>m.code===major.value);
    (row?row.children:[]).forEach(c=>{const o=document.createElement("option");o.value=c.code;o.textContent=c.label;sub.appendChild(o);});
  };
}
function renderSources(list){
  const box=$("sources");box.innerHTML="";
  list.forEach(s=>{
    const row=document.createElement("div");row.className="src";
    const cb=document.createElement("input");cb.type="checkbox";cb.id="src_"+s.source;
    cb.checked=(s.source==="europepmc"||s.source==="pubmed"||s.source==="openalex");
    const name=document.createElement("span");name.className="name";name.textContent=s.label;
    const badge=document.createElement("span");badge.className="badge";
    if(s.free){badge.textContent="免登录";badge.classList.add("ok");}
    else if(s.expired){badge.textContent="已过期，需重新配置";badge.classList.add("bad");}
    else if(s.configured){badge.textContent="已连接";badge.classList.add("ok");}
    else {badge.textContent="未配置";badge.classList.add("bad");}
    const help=document.createElement("span");help.className="hint";help.textContent=s.help;
    const btn=document.createElement("button");btn.className="mini";btn.textContent=s.free?"说明":"配置";
    btn.onclick=()=>openCred(s);
    row.append(cb,name,badge,help,btn);box.appendChild(row);
  });
}
function openCred(s){
  CRED=s;const form=$("credform");form.style.display="block";
  $("credtitle").textContent=s.label+" · 凭据";
  $("credmsg").textContent="";
  const fields=$("credfields");fields.innerHTML="";
  (s.fields||[]).forEach(f=>{
    const wrap=document.createElement("div");wrap.className="field";
    const lab=document.createElement("label");lab.textContent=f.label;
    const input=document.createElement("input");input.id="cred_"+f.key;
    input.type=(f.key==="api_key")?"password":"text";
    input.placeholder=(f.key==="expires")?"YYYY-MM-DD":"";
    wrap.append(lab,input);fields.appendChild(wrap);
  });
  form.scrollIntoView({behavior:"smooth",block:"center"});
}
$("credclose").onclick=()=>{$("credform").style.display="none";};
$("credsave").onclick=()=>{
  if(!CRED)return;
  const values={};(CRED.fields||[]).forEach(f=>{const el=$("cred_"+f.key);if(el)values[f.key]=el.value;});
  fetch("/api/credentials",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({source:CRED.source,values})}).then(r=>r.json()).then(d=>{
      if(d.error){$("credmsg").textContent=d.error;return;}
      $("credmsg").textContent="已保存到本机（不回显明文）";
      loadSettings();
    }).catch(e=>{$("credmsg").textContent=String(e);});
};
$("credclear").onclick=()=>{
  if(!CRED)return;
  fetch("/api/credentials/clear",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({source:CRED.source})}).then(()=>{$("credmsg").textContent="已清除";loadSettings();});
};
$("credtest").onclick=()=>{
  if(!CRED)return;
  $("credmsg").textContent="正在用当前保存的 Key 请求一次…";
  fetch("/api/credentials/test",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({source:CRED.source})}).then(r=>r.json()).then(d=>{
      $("credmsg").textContent=d.ok?("连接正常，返回 "+d.count+" 条"):("连接失败："+(d.error||"未知原因"));
    }).catch(e=>{$("credmsg").textContent=String(e);});
};
function renderTeam(){
  const quick=$("teamquick");quick.innerHTML="";
  (SCHEMA.identity||[]).forEach(f=>{
    const wrap=document.createElement("div");wrap.className="field";
    const lab=document.createElement("label");lab.textContent=f.label;
    let input;
    if(f.type==="select"){
      input=document.createElement("select");
      (f.options||[]).forEach(v=>{const o=document.createElement("option");o.value=v;o.textContent=v;input.appendChild(o);});
      input.value=(TEAM.identity||{})[f.key]||f.options[0];
    }else{
      input=document.createElement("input");input.type="text";input.placeholder=f.placeholder||"";
      input.value=(TEAM.identity||{})[f.key]||"";
    }
    input.id="id_"+f.key;
    wrap.append(lab,input);quick.appendChild(wrap);
  });
  const dims=$("teamdims");dims.innerHTML="";
  DIMS.forEach(d=>{
    const item=(TEAM.dims||{})[d.key]||{level:3,source:"auto",note:""};
    const div=document.createElement("div");div.className="dim";
    const top=document.createElement("div");top.className="top";
    const name=document.createElement("b");name.textContent=d.label+"（权重 "+d.weight.toFixed(2)+"）";
    const src=document.createElement("span");src.id="src_"+d.key;
    src.textContent=(item.source==="auto"?"自动推算":"手工填写")+" · "+d.hint;
    top.append(name,src);
    const sel=document.createElement("select");sel.id="dim_"+d.key;
    d.options.forEach(o=>{
      const opt=document.createElement("option");opt.value=o.level;
      opt.textContent=o.level+" 级 · "+o.label;sel.appendChild(opt);
    });
    sel.value=item.level;
    sel.dataset.source=item.source||"auto";
    const crit=document.createElement("div");crit.className="crit";crit.id="crit_"+d.key;
    const show=()=>{
      const o=d.options.find(x=>+x.level===+sel.value)||d.options[2];
      crit.textContent="判据："+o.criteria;
      src.textContent=(sel.dataset.source==="auto"?"自动推算":"手工填写")+" · "+d.hint;
      scoreTeam();
    };
    sel.onchange=()=>{sel.dataset.source="manual";show();};
    show();
    const note=document.createElement("input");note.type="text";note.id="note_"+d.key;
    note.placeholder="补充说明（可空）";note.value=item.note||"";
    div.append(top,sel,crit,note);dims.appendChild(div);
  });
  const cond=$("teamcond");cond.innerHTML="";
  (SCHEMA.conditions||[]).forEach(c=>{
    const wrap=document.createElement("div");wrap.className="field";
    const lab=document.createElement("label");lab.textContent=c.label;
    const sel=document.createElement("select");sel.id="cond_"+c.key;
    c.options.forEach(v=>{const o=document.createElement("option");o.value=v;o.textContent=v;sel.appendChild(o);});
    sel.value=(TEAM.conditions||{})[c.key]||c.options[0];
    sel.onchange=scoreTeam;
    wrap.append(lab,sel);cond.appendChild(wrap);
  });
  scoreTeam();
}
function teamIdentity(){
  const out={};(SCHEMA.identity||[]).forEach(f=>{out[f.key]=($("id_"+f.key)||{}).value||"";});return out;
}
function teamConditions(){
  const out={};(SCHEMA.conditions||[]).forEach(c=>{out[c.key]=($("cond_"+c.key)||{}).value||c.options[0];});return out;
}
function teamProfile(){
  const dims={};DIMS.forEach(d=>{
    const sel=$("dim_"+d.key);
    dims[d.key]={level:+sel.value,source:sel.dataset.source||"manual",
      note:($("note_"+d.key)||{}).value||""};
  });
  return {mode:"quick",identity:teamIdentity(),dims,conditions:teamConditions()};
}
function scoreTeam(){
  let s=0;DIMS.forEach(d=>{const sel=$("dim_"+d.key);if(sel)s+=(+sel.value||3)*d.weight;});
  const band=s>=4.2?"强":(s>=3.0?"中":"弱");
  $("teamscore").textContent="当前五维综合 "+s.toFixed(2)+" / 5（"+band+"）";
}
$("teamderive").onclick=()=>{
  fetch("/api/team/derive",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({profile:teamProfile()})}).then(r=>r.json()).then(d=>{
      if(d.error){$("teamhint").textContent=d.error;return;}
      TEAM=d.profile;renderTeam();
      $("teamhint").textContent="已按填写推算（手动改过的档位保留）";
    }).catch(e=>{$("teamhint").textContent=String(e);});
};
$("teamsave").onclick=()=>{
  fetch("/api/team",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({profile:teamProfile()})}).then(r=>r.json()).then(d=>{
      if(d.error){$("teamhint").textContent=d.error;return;}
      TEAM=d.profile;renderTeam();
      $("teamhint").textContent=`已保存 · 综合 ${d.evaluation.score} / 5（${d.evaluation.band}）`;
    });
};
loadSettings();
function loadModels(){
  fetch("/api/models").then(r=>r.json()).then(data=>{
    const sel=$("model");sel.innerHTML="";
    (data.providers||[]).forEach(p=>{
      const group=document.createElement("optgroup");
      group.label=p.label+(p.key?"":"（未配 Key）");
      (p.models||[]).forEach(m=>{
        const opt=document.createElement("option");
        opt.value=m.id;opt.textContent=m.label;
        if(m.id===data.default)opt.selected=true;
        group.appendChild(opt);
      });
      if(group.children.length)sel.appendChild(group);
    });
    if(!sel.options.length)sel.innerHTML='<option value="deepseek-flash">deepseek-flash</option>';
  }).catch(()=>{$("model").innerHTML='<option value="deepseek-flash">deepseek-flash</option>';});
}
loadModels();
function splitSections(md){
  const out=[];let cur={title:"总览",body:[]};
  md.split(/\\r?\\n/).forEach(line=>{
    if(/^##\\s+/.test(line)){out.push(cur);cur={title:line.replace(/^##\\s+/,""),body:[]};}
    else cur.body.push(line);
  });
  out.push(cur);return out.filter(s=>s.body.join("").trim());
}
function inline(s){
  s=s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  s=s.replace(/\\*\\*(.+?)\\*\\*/g,"<b>$1</b>");
  return s;
}
function render(md){
  const lines=md.split(/\\r?\\n/);const out=[];
  for(let i=0;i<lines.length;i++){
    const line=lines[i];
    if(/^###\\s+/.test(line)){out.push("<h3>"+inline(line.slice(4))+"</h3>");continue;}
    if(/^##\\s+/.test(line)){out.push("<h2>"+inline(line.slice(3))+"</h2>");continue;}
    if(/^#\\s+/.test(line)){out.push("<h2>"+inline(line.slice(2))+"</h2>");continue;}
    if(/^\\s*[-*]\\s+/.test(line)){
      const items=[];
      while(i<lines.length&&/^\\s*[-*]\\s+/.test(lines[i])){items.push("<li>"+inline(lines[i].replace(/^\\s*[-*]\\s+/,""))+"</li>");i++;}
      i--;out.push("<ul>"+items.join("")+"</ul>");continue;
    }
    if(/^\\s*\\|/.test(line)){
      const rows=[];
      while(i<lines.length&&/^\\s*\\|/.test(lines[i])){
        const cells=lines[i].split("|").slice(1,-1).map(c=>c.trim());
        if(!cells.every(c=>/^[-: ]*$/.test(c))){rows.push(cells);}
        i++;
      }
      i--;
      if(rows.length){
        let html="<table>";
        rows.forEach((cells,idx)=>{const tag=idx===0?"th":"td";html+="<tr>"+cells.map(c=>"<"+tag+">"+inline(c)+"</"+tag+">").join("")+"</tr>";});
        out.push(html+"</table>");
      }
      continue;
    }
    if(!line.trim()){continue;}
    out.push("<p>"+inline(line)+"</p>");
  }
  return out.join("\\n");
}
function showResult(res){
  $("result").style.display="block";
  const src=(res.sources||[]).map(s=>s.label+" "+s.count).join(" · ");
  $("meta").textContent=`检索 ${res.found} 篇（${src||"Europe PMC"}） · 同域 ${res.kept??res.found} 篇 · 挡掉 ${res.dropped??0} 篇 · 全文 ${res.fetched} 篇 · 卡片 ${res.cards} 张 · tokens ${res.tokens}`;
  $("dlreport").href="/api/report?id="+taskId;
  $("dlproposal").href="/api/proposal?id="+taskId;
  $("dldocx").href="/api/proposal.docx?id="+taskId;
  $("dldocx").style.display=res.proposal_docx?"inline":"none";
  Promise.all([
    fetch("/api/proposal?id="+taskId).then(r=>r.text()).catch(()=>""),
    fetch("/api/report?id="+taskId).then(r=>r.text()).catch(()=>"")
  ]).then(([pmd,rmd])=>{
    const secs=splitSections(pmd).map(s=>({title:"开题 · "+s.title,body:s.body}))
      .concat(splitSections(rmd).map(s=>({title:"证据 · "+s.title,body:s.body})));
    const tabs=$("tabs");tabs.innerHTML="";
    secs.forEach((s,i)=>{
      const b=document.createElement("button");b.textContent=s.title;
      b.onclick=()=>{[...tabs.children].forEach(x=>x.classList.remove("on"));b.classList.add("on");$("md").innerHTML=render(s.body.join("\\n"));};
      tabs.appendChild(b);if(i===0)b.click();
    });
  });
}
let liveBase=null;
function fmtSec(n){
  n=Math.max(0,Math.floor(n));
  const h=Math.floor(n/3600),m=Math.floor(n%3600/60),s=n%60;
  return h?`${h}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`:`${m}:${String(s).padStart(2,"0")}`;
}
function tickLive(){
  if(!liveBase)return;
  const d=(Date.now()-liveBase.at)/1000;
  const waited=liveBase.step_age+d;
  const hint=waited>25?"（模型还在返回，页面没死）":"";
  $("live").textContent=`已运行 ${fmtSec(liveBase.elapsed+d)} · 本步已等 ${fmtSec(waited)}${hint}`;
}
setInterval(tickLive,1000);
function renderLogs(lines){
  const box=$("log");
  const nearBottom=box.scrollTop+box.clientHeight>=box.scrollHeight-24;
  box.innerHTML="";
  (lines||[]).forEach(t=>{
    const d=document.createElement("div");
    if(t.indexOf("×")>=0||t.indexOf("失败")>=0)d.className="hit";
    d.textContent=t;
    box.appendChild(d);
  });
  if(nearBottom)box.scrollTop=box.scrollHeight;
}
function poll(){
  fetch("/api/status?id="+taskId).then(r=>r.json()).then(s=>{
    $("fill").style.width=s.percent+"%";$("pct").textContent=s.percent+"%";
    $("step").textContent=s.step;$("detail").textContent=s.detail;
    liveBase={elapsed:s.elapsed||0,step_age:s.step_age||0,at:Date.now()};
    tickLive();
    renderLogs(s.logs);
    if(s.error){liveBase=null;$("error").textContent=s.error;clearInterval(timer);$("run").disabled=false;return;}
    if(s.done){liveBase=null;clearInterval(timer);$("run").disabled=false;showResult(s.result);}
  }).catch(e=>{$("error").textContent=String(e);clearInterval(timer);$("run").disabled=false;});
}
$("run").onclick=()=>{
  const direction=$("direction").value.trim();
  if(!direction){alert("请先写一个研究方向");return;}
  const from=$("year_from").value, to=$("year_to").value;
  if(!from||!to){alert("请选择年份范围的起止日期");return;}
  const fy=+from.slice(0,4), ty=+to.slice(0,4);
  if(fy>ty){alert("起始年份不能晚于结束年份");return;}
  $("run").disabled=true;$("result").style.display="none";$("error").textContent="";
  $("progress").style.display="block";$("fill").style.width="0";$("pct").textContent="0%";$("step").textContent="提交中";
  $("log").innerHTML="";$("live").textContent="";liveBase=null;
  const sources=[].slice.call($("sources").querySelectorAll("input[type=checkbox]"))
    .filter(c=>c.checked).map(c=>c.id.replace("src_",""));
  if(!sources.length){alert("至少勾一个检索源");return;}
  const cond=teamConditions();
  const payload={direction,domain_key:$("domain").value,platform:cond.experiment,budget:cond.budget,period:cond.period,
    wet_lab:cond.wet,years:`${fy}-${ty}`,search_limit:+$("search").value,
    fetch_limit:+$("fetch").value,card_limit:+$("cards").value,model_name:$("model").value,
    sources,oecd:$("oecd_sub").value,team_profile:teamProfile(),owner:$("owner").value};
  fetch("/api/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})
    .then(r=>r.json()).then(d=>{taskId=d.id;timer=setInterval(poll,1200);poll();})
    .catch(e=>{$("error").textContent=String(e);$("run").disabled=false;});
};
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "LitRadar/0.3"

    def log_message(self, fmt: str, *args) -> None:  # 静默，避免刷屏
        return

    def _send(self, code: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # 面板跑在 DSH（另一个端口）里，健康探针需要跨域放行；服务只绑 127.0.0.1。
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json(self, data: dict, code: int = 200) -> None:
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path)
        query = parse_qs(route.query)
        if route.path == "/":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if route.path == "/api/models":
            try:
                self._json(list_models())
            except Exception as exc:  # noqa: BLE001
                self._json({"error": f"读取 DSH 模型配置失败：{exc}"}, 500)
            return
        if route.path == "/api/health":
            try:
                _, api_key, model = resolve_model("deepseek")
                has_key = bool(api_key)
            except Exception:
                model, has_key = "", False
            self._json({"ok": True, "app": "litradar", "model": model, "key": has_key})
            return
        if route.path == "/api/status":
            task_id = (query.get("id") or [""])[0]
            with LOCK:
                task = TASKS.get(task_id)
            if not task:
                self._json({"error": "任务不存在"}, 404)
                return
            self._json({k: task[k] for k in ("step", "detail", "percent", "done", "error", "result")}
                       | {"logs": task.get("logs", [])[-80:],
                          "elapsed": int(time.time() - task.get("t0", time.time())),
                          "step_age": int(time.time() - task.get("last", time.time()))})
            return
        if route.path == "/api/report":
            task_id = (query.get("id") or [""])[0]
            with LOCK:
                task = TASKS.get(task_id)
            if not task or not task.get("result"):
                self._json({"error": "还没有结果"}, 404)
                return
            path = Path(task["result"]["report"])
            self._send(200, path.read_bytes(), "text/markdown; charset=utf-8")
            return
        if route.path == "/api/download":
            task_id = (query.get("id") or [""])[0]
            with LOCK:
                task = TASKS.get(task_id)
            if not task or not task.get("result"):
                self._json({"error": "还没有结果"}, 404)
                return
            path = Path(task["result"]["report"])
            body = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="litradar-report.md"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if route.path == "/api/settings":
            self._json({"sources": credentials.all_status(),
                        "team": {"profile": team.load(), "schema": team.schema(),
                                 "evaluation": team.evaluate()},
                        "oecd": oecd.as_json()})
            return
        if route.path == "/api/proposal":
            task_id = (query.get("id") or [""])[0]
            with LOCK:
                task = TASKS.get(task_id)
            if not task or not task.get("result") or not task["result"].get("proposal"):
                self._json({"error": "还没有开题报告"}, 404)
                return
            self._send(200, Path(task["result"]["proposal"]).read_bytes(),
                       "text/markdown; charset=utf-8")
            return
        if route.path == "/api/proposal.docx":
            task_id = (query.get("id") or [""])[0]
            with LOCK:
                task = TASKS.get(task_id)
            path = (task or {}).get("result", {}).get("proposal_docx") if task else ""
            if not path or not Path(path).exists():
                self._json({"error": "没有 Word 版（可能未装 python-docx）"}, 404)
                return
            body = Path(path).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type",
                             "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            self.send_header("Content-Disposition", 'attachment; filename="litradar-proposal.docx"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        origin = self.headers.get("Origin") or ""
        if origin and not any(h in origin for h in ("127.0.0.1", "localhost")):
            self._json({"error": "只接受本机页面调用"}, 403)
            return
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        if path == "/api/credentials":
            source = str(payload.get("source") or "")
            if source not in credentials.SPECS:
                self._json({"error": "未知检索源"}, 400)
                return
            try:
                self._json({"status": credentials.save(source, payload.get("values") or {})})
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, 500)
            return
        if path == "/api/credentials/clear":
            source = str(payload.get("source") or "")
            self._json({"status": credentials.clear(source)})
            return
        if path == "/api/credentials/test":
            source = str(payload.get("source") or "")
            try:
                papers, stats = search_all("machine learning", ["machine learning"],
                                           "2024-2026", 3, [source])
                ok = bool(stats and stats[0]["ok"])
                self._json({"ok": ok, "count": len(papers),
                            "error": "" if ok else (stats[0]["error"] if stats else "无响应")})
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "count": 0, "error": str(exc)[:160]})
            return
        if path == "/api/team":
            profile = team.save(payload.get("profile") or {})
            self._json({"profile": profile, "evaluation": team.evaluate(profile)})
            return
        if path == "/api/team/derive":
            profile = team.save(team.quick_derive(payload.get("profile") or {}))
            self._json({"profile": profile, "evaluation": team.evaluate(profile)})
            return
        if path != "/api/run":
            self._json({"error": "not found"}, 404)
            return
        direction = str(payload.get("direction") or "").strip()
        if not direction:
            self._json({"error": "缺少研究方向"}, 400)
            return
        task_id = uuid.uuid4().hex[:12]
        now = time.time()
        with LOCK:
            TASKS[task_id] = {"step": "排队中", "detail": "", "percent": 0,
                              "done": False, "error": "", "result": None,
                              "logs": [], "t0": now, "last": now}

        def _log(text: str) -> None:
            line = f"{time.strftime('%H:%M:%S')}  {text}"
            with LOCK:
                task = TASKS.get(task_id)
                if task is None:
                    return
                task["logs"].append(line)
                del task["logs"][:-200]

        def progress(step: str, detail: str, percent: int) -> None:
            with LOCK:
                task = TASKS[task_id]
                changed = (task["step"], task["detail"], task["percent"]) != (step, detail, percent)
                task.update(step=step, detail=detail, percent=percent, last=time.time())
            if changed:
                _log(f"[{step}] {detail}")

        def note(text: str) -> None:
            _log(text)

        def worker() -> None:
            set_activity(note)
            try:
                result = run_pipeline(
                    direction,
                    platform=payload.get("platform", "不限"),
                    budget=payload.get("budget", "不限"),
                    period=payload.get("period", "不限"),
                    wet_lab=payload.get("wet_lab", "接受"),
                    years=payload.get("years", ""),
                    search_limit=int(payload.get("search_limit", 40)),
                    fetch_limit=int(payload.get("fetch_limit", 8)),
                    card_limit=int(payload.get("card_limit", 8)),
                    model_name=payload.get("model_name", "deepseek"),
                    db_path=DB_PATH,
                    domain_key=payload.get("domain_key", "auto"),
                    sources_list=payload.get("sources") or ["europepmc"],
                    oecd_code=str(payload.get("oecd") or ""),
                    team_profile=payload.get("team_profile") or team.load(),
                    owner=str(payload.get("owner") or ""),
                    progress=progress,
                    note=note,
                )
                with LOCK:
                    TASKS[task_id].update(done=True, result=result, percent=100, step="完成")
                _log("完成：简报与 CSV 已写入 runs 目录")
            except Exception as exc:  # noqa: BLE001
                with LOCK:
                    TASKS[task_id].update(error=f"{exc}\n{traceback.format_exc(limit=3)}",
                                          done=True, step="失败")
                _log(f"× 失败：{str(exc)[:120]}")
            finally:
                set_activity(None)

        threading.Thread(target=worker, daemon=True).start()
        self._json({"id": task_id})


def serve(host: str = "127.0.0.1", port: int = 8899) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"LitRadar 界面已启动：http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()

from __future__ import annotations

import json
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import credentials, identity, oecd, team
from .config import DB_PATH
from .llm import resolve_model, set_activity
from .model_catalog import list_models
from .pipeline import run_pipeline
from .sources import search_all

TASKS: dict[str, dict] = {}
LOCK = threading.Lock()


def _derive_team(payload: dict) -> tuple[dict, dict, str]:
    """把页面填的条件与可检索到的作者证据合起来推算五维。

    只有高置信、唯一的作者候选才会自动带入；候选不唯一时不替用户选人。
    """
    profile = team.quick_derive(payload.get("profile") or {})
    evidence: dict = {}
    note = ""
    try:
        identity_row = profile.get("identity") or {}
        author_id = str(identity_row.get("author_openalex") or "")
        if not author_id and identity_row.get("author") and identity_row.get("unit"):
            found = identity.lookup("search", {
                "name": identity_row.get("author"), "unit": identity_row.get("unit"),
                "orcid": identity_row.get("author_orcid") or "",
            })
            if found.get("error"):
                note = str(found["error"])
            else:
                authors = found.get("authors") or []
                high = [row for row in authors if row.get("confidence") == "高"]
                if len(high) == 1:
                    row = high[0]
                    author_id = str(row.get("id") or "")
                    identity_row["author_openalex"] = author_id
                    identity_row["author_orcid"] = str(row.get("orcid") or "")
                    identity_row["author_works_count"] = str(row.get("works_count") or "")
                    identity_row["lookup_confidence"] = "高"
                    identity_row["lookup_note"] = ("OpenAlex " + author_id +
                                                  "；作者候选自动带入，仍需确认")
                    note = "已用唯一高置信作者候选补充证据"
                elif authors:
                    note = "作者候选不唯一，未自动选人；先在上方确认作者，再重新推算"
        if author_id:
            works = identity.author_works(author_id, identity_row.get("author") or "",
                                          identity_row.get("unit") or "",
                                          identity_row.get("unit_ror") or "")
            evidence = team.evidence_from_works(works, identity_row)
            if not identity_row.get("representative") and works.get("representative_suggestion"):
                identity_row["representative"] = str(works["representative_suggestion"])[:220]
            if not identity_row.get("org") and works.get("platform_hint"):
                identity_row["org"] = str(works["platform_hint"])
            note = "；".join(x for x in (note, evidence.get("note", "")) if x)
        elif not note:
            note = "未取到作者 ID；先按填写推算，填单位与通讯作者后可再检索补充"
        profile = team.quick_derive(profile, evidence)
    except Exception as exc:  # noqa: BLE001 - 检索失败退回规则推算
        note = f"检索补充失败，已按填写推算：{str(exc)[:120]}"
        profile = team.quick_derive(payload.get("profile") or {})
    return profile, evidence, note


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
#teamderive{flex:0 0 auto;white-space:nowrap;padding:8px 16px;font-size:13px;background:var(--accent);color:#fff}
.ghost{background:#fff;color:var(--sub);border:1px solid var(--line)}
.cred{margin-top:12px;padding-top:12px;border-top:1px solid var(--line)}
.credhead{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.dim{border:1px solid var(--line);border-radius:6px;padding:10px 12px;margin-bottom:9px;background:#fbfbfc}
.dim .top{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}
.dim .top b{font-size:13px}
.dim .top span{font-size:12px;color:var(--sub)}
.dim select{width:100%;margin-top:6px}
.dim .crit{margin-top:5px;font-size:12px;color:var(--sub)}
.lookup{border:1px solid var(--line);background:#fbfbfc;border-radius:8px;padding:12px;margin:12px 0}
.lookup .grid{grid-template-columns:repeat(2,1fr)}
.profilebox{margin:0 0 6px}
.profilebox .match{margin:0}
.suggest{position:relative;margin-top:5px}
.suggest .item{border:1px solid var(--line);border-radius:6px;padding:8px 10px;margin:5px 0;background:#fff;cursor:pointer}
.suggest .item:hover{border-color:var(--accent);background:#f7fbf9}
.suggest .item b{font-size:13px}
.suggest .item .meta{font-size:12px;color:var(--sub);margin-top:3px}
.suggest .item .pick{float:right;font-size:12px;color:var(--accent)}
.match{border:1px solid var(--line);border-radius:6px;padding:9px 11px;margin:8px 0;background:#fff}
.match .row{display:flex;align-items:flex-start;gap:9px}
.match input[type=radio]{margin-top:5px}
.match b{font-size:14px}
.match .meta{font-size:12px;color:var(--sub);margin-top:4px}
.match .acts{display:flex;flex-wrap:wrap;gap:7px;margin-top:7px}
.match .acts button{padding:4px 10px;font-size:12px;background:#eef1f4;color:var(--ink)}
.chip{display:inline-block;border:1px solid var(--line);background:#fff;border-radius:12px;padding:2px 9px;margin:3px 4px 0 0;font-size:12px;cursor:pointer}
.chip:hover{border-color:var(--accent);color:var(--accent)}
.work{padding:7px 0;border-bottom:1px dashed var(--line);font-size:13px}
.work:last-child{border-bottom:0}
.work .tagline{font-size:12px;color:var(--sub)}
.good{color:var(--accent)} .bad{color:var(--warn)}
.foot{margin-top:34px;color:var(--sub);font-size:12px}
</style>
</head>
<body>
<div class="wrap">
<header><h1>题眼 LitRadar</h1><span class="tag">一个方向进去，一套能开题的证据包出来</span></header>

<div class="panel">
<div class="grid">
  <div class="field full">
    <label>研究方向（必填，按“研究对象 + 科学问题 + 目标/方法”写一句话）</label>
    <textarea id="direction" placeholder="例：高温合金涡轮盘的组织演化与疲劳寿命预测
例：城市热岛的形成机制与调控路径
例：平台经济中算法定价的福利效应与监管设计"></textarea>
  </div>
  <div class="field span2"><label>OECD 学科大类（Frascati 2007，必选）</label><select id="oecd_major"><option value="">请选择</option></select></div>
  <div class="field"><label>OECD 子类（必选，决定检索口径与卡片语义）</label><select id="oecd_sub"><option value="">先选大类</option></select></div>
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
<p class="hint">按权威程度排序：一级索引（WOS、Scopus）→ 中文核心平台（CNKI、CSCD、CSSCI）→ 中文全文库（万方、维普）→ 专业文摘（PubMed、Europe PMC）→ 开放元数据（Crossref、OpenAlex、Semantic Scholar）→ 预印本（arXiv）。WOS/Scopus 填 API Key；CNKI 等走校园网/VPN，不保存账号密码。</p>
<div id="sources"></div>
<div id="credform" class="cred" style="display:none">
  <div class="credhead"><b id="credtitle"></b><button class="mini" id="credclose">收起</button></div>
  <div id="credfields" class="grid"></div>
  <div class="actions"><button id="credsave">保存到本机</button><button class="ghost" id="credtest">测试连接</button><button class="ghost" id="credclear">清除</button><span class="hint" id="credmsg"></span></div>
</div>
</div>

<div class="panel">
<h2 class="sect">课题组条件（基金评审五维 + 研究条件）</h2>
<p class="hint">先输入单位与通讯作者，在下拉里选中规范记录；再点“生成课题组画像”。插件会补院系、平台、近作与五维依据；只用于本次推算，刷新后恢复默认。</p>
<div class="grid" id="teamquick"></div>
<div class="actions" style="margin:14px 0 8px">
  <button class="mini" id="teamderive">生成课题组画像</button>
  <span class="hint" id="teamhint">五维随单位、作者与条件填写更新；本次填写只在页面内，刷新后恢复默认</span>
</div>
<div class="hint" id="lookmsg" style="margin:4px 0 8px"></div>
<div id="lookbox" class="profilebox"></div>
<h3 class="sect" style="margin-top:16px">五维画像</h3>
<div id="teamdims" style="margin-top:14px"></div>
<h3 class="sect" style="margin-top:16px">研究条件</h3>
<p class="hint">研究类型、数据来源、平台使用、经费与周期、伦理合规、报告规范和数据管理逐项核对；判据写进开题报告。这些条件只用于本次运行，不落盘。</p>
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
let CRED=null, DIMS=[], SCHEMA=null, TEAM=null, VERIFIED={}, STALE=[];
let teamTimer=null, teamSeq=0, suggestTimer=null, suggestSeq=0;
function loadSettings(){
  fetch("/api/settings").then(r=>r.json()).then(d=>{
    buildOecd(d.oecd||[]);
    STALE=(d.expired_sources||[]).map(x=>x.source);
    renderSources(d.sources||[]);
    SCHEMA=d.team.schema||{identity:[],dimensions:[],conditions:[]};
    DIMS=SCHEMA.dimensions||[];
    TEAM=d.team.profile||{identity:{},dims:{},conditions:{}};
    VERIFIED=syncVerified(TEAM.identity||{});
    renderTeam();
    if(STALE.length){
      const src=(d.sources||[]).find(x=>x.source===STALE[0]);
      if(src){
        openCred(src);
        $("credmsg").textContent="登录信息已过期，旧凭据已自动清除；请重新填写并保存。";
      }
    }
  }).catch(e=>{$("sources").textContent="读取配置失败："+e;});
}
function buildOecd(rows){
  const major=$("oecd_major");major.innerHTML='<option value="">请选择</option>';
  rows.forEach(m=>{const o=document.createElement("option");o.value=m.code;o.textContent=m.label;major.appendChild(o);});
  major.onchange=()=>{
    const sub=$("oecd_sub");sub.innerHTML='<option value="">请选择子类</option>';
    const row=rows.find(m=>m.code===major.value);
    (row?row.children:[]).forEach(c=>{const o=document.createElement("option");o.value=c.code;o.textContent=c.label;sub.appendChild(o);});
  };
}
function renderSources(list){
  const box=$("sources");box.innerHTML="";
  list.forEach(s=>{
    const row=document.createElement("div");row.className="src";
    if(s.direct){
      const cb=document.createElement("input");cb.type="checkbox";cb.id="src_"+s.source;
      cb.checked=["openalex","crossref","pubmed","europepmc"].includes(s.source);
      row.append(cb);
    }else{
      const lock=document.createElement("span");lock.className="badge";lock.textContent="机构订阅";
      row.append(lock);
    }
    const name=document.createElement("span");name.className="name";name.textContent=s.label;
    const tier=document.createElement("span");tier.className="badge";tier.textContent=s.tier||"";
    const badge=document.createElement("span");badge.className="badge";
    if(s.access==="subscription"){badge.textContent="校园网/VPN";badge.classList.add("ok");}
    else if(s.access==="open"){badge.textContent="免登录";badge.classList.add("ok");}
    else if(STALE.includes(s.source)){badge.textContent="待重新登录";}
    else if(s.expired){badge.textContent="已过期，需重新配置";badge.classList.add("bad");}
    else if(s.configured){badge.textContent="已连接";badge.classList.add("ok");}
    else {badge.textContent="未配置";badge.classList.add("bad");}
    const help=document.createElement("span");help.className="hint";
    help.textContent=(s.scope?("覆盖："+s.scope+"；"):"")+(s.help||"");
    const btn=document.createElement("button");btn.className="mini";
    btn.textContent=s.direct?(s.access==="open"?"说明":"配置"):"机构入口";
    btn.onclick=()=>{
      if(!s.direct&&s.url){window.open(s.url,"_blank","noopener");return;}
      openCred(s);
    };
    const note=document.createElement("div");note.className="hint";note.style.width="100%";
    note.textContent=s.note||"";
    row.append(name,tier,badge,help,btn,note);box.appendChild(row);
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
    input.autocomplete="off";
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
      (CRED.fields||[]).forEach(f=>{const el=$("cred_"+f.key);if(el)el.value="";});
      $("credmsg").textContent="已保存到本机（长期有效；过期会自动清除，不回显明文）";
      loadSettings();
    }).catch(e=>{$("credmsg").textContent=String(e);});
};
$("credclear").onclick=()=>{
  if(!CRED)return;
  fetch("/api/credentials/clear",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({source:CRED.source})}).then(()=>{
      (CRED.fields||[]).forEach(f=>{const el=$("cred_"+f.key);if(el)el.value="";});
      $("credmsg").textContent="已清除";
      loadSettings();
    });
};
$("credtest").onclick=()=>{
  if(!CRED)return;
  $("credmsg").textContent="正在用当前保存的 Key 请求一次…";
  fetch("/api/credentials/test",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({source:CRED.source})}).then(r=>r.json()).then(d=>{
      $("credmsg").textContent=d.ok?("连接正常，返回 "+d.count+" 条"):("连接未通过："+(d.error||"未知原因"));
    }).catch(e=>{$("credmsg").textContent=String(e);});
};
function esc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
function syncVerified(id){
  const keys=["unit_ror","unit_official","author_openalex","author_orcid","author_doi",
    "author_works_count","lookup_confidence","lookup_note","author_name"];
  const out={};keys.forEach(k=>{if(id&&id[k])out[k]=id[k];});return out;
}
function deptFromUnit(original, official, zh){
  const candidates=[official,zh].filter(Boolean).sort((a,b)=>b.length-a.length);
  const text=String(original||"").trim();
  for(const c of candidates){
    const at=text.indexOf(c);
    if(at>=0){
      const rest=text.slice(at+c.length).replace(/^[\\s,，;；/、\\-]+/,"").trim();
      if(rest)return rest;
    }
  }
  return "";
}
function hideSuggest(key){
  const el=$("sug_"+key);if(el)el.innerHTML="";
}
function scheduleSuggest(key){
  clearTimeout(suggestTimer);
  suggestTimer=setTimeout(()=>loadSuggestions(key),380);
}
function loadSuggestions(key){
  const unit=($("id_unit")&&$("id_unit").value||"").trim();
  const name=($("id_author")&&$("id_author").value||"").trim();
  const q=key==="unit"?unit:name;
  const box=$("sug_"+key);
  if(!box)return;
  if(q.length<2){box.innerHTML="";return;}
  const seq=++suggestSeq;
  box.innerHTML='<div class="meta">正在检索…</div>';
  fetch("/api/identity",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({action:"search",unit:key==="unit"?unit:unit,name:key==="author"?name:"",
      orcid:"",doi:"",ror:VERIFIED.unit_ror||""})}).then(r=>r.json()).then(d=>{
    if(seq!==suggestSeq)return;
    if(d.error){box.innerHTML='<div class="bad">'+esc(d.error)+'</div>';return;}
    let rows=[];
    if(key==="unit"){
      rows=(d.institutions||[]).slice(0,5).map(inst=>({
        html:'<b>'+esc(inst.name||inst.name_zh)+'</b><span class="pick">采用</span>'+
          '<div class="meta">'+esc([inst.name_zh,inst.country_name,inst.type,
          inst.ror?("ROR "+inst.ror):""].filter(Boolean).join(" · "))+'</div>',
        click:()=>selectInstitution(inst)
      }));
      if(!rows.length)box.innerHTML='<div class="meta">ROR 没匹配到单位，补官方英文名或直接手填。</div>';
    }else{
      rows=(d.authors||[]).slice(0,5).map(a=>({
        html:'<b>'+esc(a.name)+'</b><span class="pick">'+esc(a.confidence||"")+'置信度 · 采用</span>'+
          '<div class="meta">'+esc([(a.institutions||[]).map(x=>x.name).slice(0,2).join("；"),
          a.orcid?("ORCID "+a.orcid):"",a.works_count+" 篇"].filter(Boolean).join(" · "))+'</div>',
        click:()=>selectAuthor(a)
      }));
      if(!rows.length)box.innerHTML='<div class="meta">没有作者候选；补 ORCID，或用论文英文署名再试。</div>';
    }
    box.innerHTML="";rows.forEach(r=>{
      const item=document.createElement("div");item.className="item";item.innerHTML=r.html;
      item.onclick=r.click;box.appendChild(item);
    });
  }).catch(e=>{if(seq===suggestSeq)box.innerHTML='<div class="bad">检索失败：'+esc(e)+'</div>';});
}
function selectInstitution(inst){
  const original=$("id_unit").value.trim();
  const dept=deptFromUnit(original,inst.name,inst.name_zh);
  const newRor=inst.id||"";
  let msg="已采用单位："+(inst.name||inst.name_zh);
  if(VERIFIED.unit_ror&&VERIFIED.unit_ror!==newRor){
    VERIFIED.author_openalex="";VERIFIED.author_orcid="";
    VERIFIED.author_works_count="";VERIFIED.author_doi="";
    VERIFIED.lookup_confidence="";
    msg="单位已更新；请重新选择通讯作者。";
  }
  $("id_unit").value=inst.name||inst.name_zh||original;
  if(dept&&$("id_department"))$("id_department").value=dept;
  VERIFIED.unit_ror=newRor;
  VERIFIED.unit_official=inst.name||inst.name_zh||"";
  VERIFIED.lookup_confidence="单位已核验";
  VERIFIED.lookup_note="ROR "+(inst.ror||"")+"；"+(inst.country_name||"")+
    (inst.website?("；"+inst.website):"");
  $("lookmsg").textContent=msg;
  $("lookmsg").classList.add("good");
  hideSuggest("unit");
  $("lookbox").innerHTML='<div class="match"><b>课题组画像 · 单位</b><div class="meta">'+
    esc(inst.name||inst.name_zh)+' · ROR '+esc(inst.ror||"")+
    (dept?(' · 院系 '+esc(dept)):'')+'</div></div>'+
    '<div id="workpanel" class="match" style="display:none"></div>';
  if($("id_author")&&$("id_author").value.trim())scheduleTeam();
}
function setOrg(level){
  const sel=$("id_org");
  if(!sel||!level)return;
  [...sel.options].forEach(o=>{if(o.value===level)sel.value=level;});
  $("lookmsg").textContent="平台层级已设为："+sel.value+"（可再手改）";
  scheduleTeam();
}
function selectAuthor(a){
  $("id_author").value=a.name||"";
  VERIFIED.author_openalex=a.id||"";
  VERIFIED.author_orcid=a.orcid||"";
  VERIFIED.author_name=a.name||"";
  VERIFIED.author_works_count=String(a.works_count||"");
  VERIFIED.author_doi="";
  VERIFIED.lookup_confidence=a.confidence||"";
  VERIFIED.lookup_note="OpenAlex "+(a.id||"")+(a.orcid?("；ORCID "+a.orcid):"")+
    "；作品 "+a.works_count+" 篇";
  $("lookmsg").textContent="已采用作者："+a.name+"（"+a.confidence+"置信度），正在取近作…";
  hideSuggest("author");
  const box=$("lookbox");
  const old=$("workpanel");if(old)old.remove();
  const panel=document.createElement("div");panel.className="match";panel.id="workpanel";
  panel.innerHTML='<div class="meta">正在读取近作…</div>';box.appendChild(panel);
  fetch("/api/identity",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({action:"works",author_id:a.id,name:a.name,
      unit:$("id_unit").value,ror:VERIFIED.unit_ror||""})}).then(r=>r.json()).then(d=>{
    renderWorks(d,a);
    scheduleTeam();
  }).catch(e=>{panel.innerHTML='<div class="bad">近作读取失败：'+esc(e)+'</div>';});
}
function renderWorks(d,a){
  const panel=$("workpanel");if(!panel)return;
  if(d.error){panel.innerHTML='<div class="bad">'+esc(d.error)+'</div>';return;}
  let autoDept=false;
  if(d.departments&&d.departments.length&&$("id_department")&&!$("id_department").value.trim()){
    $("id_department").value=d.departments[0].value;autoDept=true;
  }
  let html='<div class="meta"><b>'+esc(a.name)+'</b> 近作 · 通讯标记来自 OpenAlex，仍需按出版社页面核对。</div>';
  if(d.departments&&d.departments.length){
    html+='<div class="meta">论文里出现的院系写法（已按最高频自动填入，可点其他写法改）：</div>';
    d.departments.forEach(x=>{
      html+='<span class="chip" data-dept="'+esc(x.value)+'">'+esc(x.value)+
        ' <span class="hint">'+x.count+' 次</span></span>';
    });
  }
  if(d.platform_hint){
    html+='<div class="acts"><button class="mini ghost" data-org="'+esc(d.platform_hint)+'">采用平台层级：'+
      esc(d.platform_hint)+'</button></div>';
  }
  const displayWorks=(d.works||[]).filter(w=>{
    const t=String(w.title||"").trim().toLowerCase();
    return !["erratum","correction","retraction","editorial","comment","reply"].some(k=>t.startsWith(k));
  });
  html+='<div style="margin-top:8px">';
  displayWorks.forEach(w=>{
    const pos={first:"第一作者",middle:"中间作者",last:"末位作者"}[w.position]||w.position||"";
    html+='<div class="work"><b>'+esc(w.title||"(无题)")+'</b>'+
      '<div class="tagline">'+w.year+' · '+esc(w.journal||"")+' · '+esc(pos)+
      (w.is_corresponding?' · <span class="good">通讯作者</span>':'')+
      (w.doi?' · DOI '+esc(w.doi):'')+'</div></div>';
  });
  html+='</div>';
  if(!displayWorks.length)html+='<div class="meta">没有可显示的研究性近作；代表作请按实际补写。</div>';
  if(d.representative_suggestion){
    html+='<div class="acts"><button class="mini" id="useRep">带入代表作候选</button></div>';
  }
  const first=(d.works||[]).find(w=>w.is_corresponding)||(d.works||[])[0]||{};
  panel.innerHTML=html;
  panel.querySelectorAll("[data-dept]").forEach(el=>{
    el.onclick=()=>{if($("id_department"))$("id_department").value=el.dataset.dept;
      $("lookmsg").textContent="院系已填入："+el.dataset.dept;};
  });
  panel.querySelectorAll("[data-org]").forEach(el=>{
    el.onclick=()=>setOrg(el.dataset.org);
  });
  const use=$("useRep");
  if(use)use.onclick=()=>{
    $("id_representative").value=d.representative_suggestion||"";
    VERIFIED.author_doi=first.doi||"";
    VERIFIED.lookup_confidence=(VERIFIED.lookup_confidence||"中")+"；代表作已带入";
    $("lookmsg").textContent="代表作候选已填入，个人贡献请按实际补写。";
  };
  if($("lookmsg"))$("lookmsg").textContent="已采用作者："+(a.name||"")+"；近作已读取"+
    (autoDept?"；院系按论文高频写法自动填入，可改":"")+"。";
}
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
    if(f.key==="unit"||f.key==="author"){
      input.autocomplete="off";
      input.oninput=()=>scheduleSuggest(f.key);
      const sug=document.createElement("div");sug.className="suggest";sug.id="sug_"+f.key;
      wrap.append(lab,input,sug);quick.appendChild(wrap);
      return;
    }
    input.onchange=scheduleTeam;
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
  let lastGroup="";
  (SCHEMA.conditions||[]).forEach(c=>{
    if(c.group&&c.group!==lastGroup){
      lastGroup=c.group;
      const head=document.createElement("div");head.className="field full";
      head.innerHTML='<label style="font-weight:600;color:var(--ink)">'+c.group+'</label>';
      cond.appendChild(head);
    }
    const wrap=document.createElement("div");wrap.className="field";
    const lab=document.createElement("label");lab.textContent=c.label;
    const sel=document.createElement("select");sel.id="cond_"+c.key;
    c.options.forEach(v=>{const o=document.createElement("option");o.value=v;o.textContent=v;sel.appendChild(o);});
    sel.value=(TEAM.conditions||{})[c.key]||c.options[0];
    sel.onchange=()=>{scoreTeam();scheduleTeam();};
    wrap.append(lab,sel);cond.appendChild(wrap);
  });
  scoreTeam();
}
function teamIdentity(){
  const out={};(SCHEMA.identity||[]).forEach(f=>{out[f.key]=($("id_"+f.key)||{}).value||"";});
  if(VERIFIED.unit_official&&out.unit!==VERIFIED.unit_official){
    VERIFIED.unit_ror="";VERIFIED.unit_official="";VERIFIED.lookup_confidence="";
  }
  if(VERIFIED.author_name&&out.author!==VERIFIED.author_name){
    VERIFIED.author_openalex="";VERIFIED.author_orcid="";VERIFIED.author_works_count="";
    VERIFIED.lookup_confidence="";VERIFIED.author_doi="";
  }
  Object.assign(out,VERIFIED);
  return out;
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
function scheduleTeam(){
  clearTimeout(teamTimer);
  teamTimer=setTimeout(()=>deriveTeam(false),650);
}
function deriveTeam(manual){
  const seq=++teamSeq;
  if(manual)$("teamhint").textContent="正在核对作者近作、单位平台与五维判据…";
  fetch("/api/team/derive",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({profile:teamProfile()})}).then(r=>r.json()).then(d=>{
      if(seq!==teamSeq)return;
      if(d.error){if(manual)$("teamhint").textContent=d.error;return;}
      TEAM=d.profile;VERIFIED=syncVerified(TEAM.identity||{});renderTeam();
      $("teamhint").textContent=d.note||"已按填写重新推算（手动改过的档位保留）";
    }).catch(e=>{if(manual)$("teamhint").textContent=String(e);});
}
$("teamderive").onclick=()=>deriveTeam(true);
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
  if(!$("oecd_sub").value){alert("请选择 OECD 子类：它决定检索口径与卡片字段");return;}
  const from=$("year_from").value, to=$("year_to").value;
  if(!from||!to){alert("请选择年份范围的起止日期");return;}
  const fy=+from.slice(0,4), ty=+to.slice(0,4);
  if(fy>ty){alert("起始年份不能晚于结束年份");return;}
  $("run").disabled=true;$("result").style.display="none";$("error").textContent="";
  $("progress").style.display="block";$("fill").style.width="0";$("pct").textContent="0%";$("step").textContent="提交中";
  $("log").innerHTML="";$("live").textContent="";liveBase=null;
  const sources=[].slice.call($("sources").querySelectorAll("input[type=checkbox]"))
    .filter(c=>c.checked).map(c=>c.id.replace("src_",""));
  if(!sources.length){alert("至少勾一个可直接检索的源；CNKI 等机构订阅源请在校园网/VPN 入口核对题录");$("run").disabled=false;return;}
  const cond=teamConditions();
  const payload={direction,domain_key:"auto",platform:cond.experiment,budget:cond.budget,period:cond.period,
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
    server_version = "LitRadar/0.10"

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
            stale = credentials.clear_expired()
            base_team = team.defaults()
            self._json({"sources": credentials.all_status(),
                        "expired_sources": stale,
                        "team": {"profile": base_team, "schema": team.schema(),
                                 "evaluation": team.evaluate(base_team)},
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
        if path == "/api/identity":
            try:
                self._json(identity.lookup(str(payload.get("action") or "search"), payload))
            except Exception as exc:  # noqa: BLE001
                self._json({"error": f"身份检索失败：{str(exc)[:200]}"}, 500)
            return
        if path == "/api/team":
            profile = team.quick_derive(payload.get("profile") or {})
            self._json({"profile": profile, "evaluation": team.evaluate(profile)})
            return
        if path == "/api/team/derive":
            profile, evidence, note = _derive_team(payload)
            self._json({"profile": profile, "evaluation": team.evaluate(profile),
                        "evidence": evidence, "note": note})
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
                    team_profile=payload.get("team_profile") or team.defaults(),
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

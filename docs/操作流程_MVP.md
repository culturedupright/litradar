# 手把手：从零把这个工具做出来

> 适用：Windows 10/11，Python 3.10+，每天能投入 3–4 小时。
> 目标：20 天后，你能对着一个研究方向跑出「检索 → 筛选 → 抓全文和图 → 抽卡片 → 导出简报」。
> 所有命令都在 **PowerShell** 里执行，路径默认 `C:\Users\1\Desktop\工作\26秋ai比赛\07_MVP_文献流水线`。

---

## 目录

- 阶段 0：准备环境（约 1 小时）
- 阶段 1：让检索跑起来（第 1–2 天）
- 阶段 2：筛选（第 3 天）
- 阶段 3：抓全文与图（第 4–6 天）
- 阶段 4：抽卡片（第 7–10 天，最花时间）
- 阶段 5：导出简报（第 11–12 天）
- 阶段 6：批量与稳定性（第 13–16 天）
- 阶段 7：套界面（第 17–18 天，可砍）
- 阶段 8：交卷（第 19–20 天）
- 附录：常见报错对照表

---

# 阶段 0：准备环境

## 0.1 确认 Python

```powershell
python --version
```

看到 `Python 3.10.x` 以上即可。没有就去 https://www.python.org/downloads/ 装，**安装时勾选 Add python.exe to PATH**。

## 0.2 建目录

```powershell
cd "C:\Users\1\Desktop\工作\26秋ai比赛"
mkdir 07_MVP_文献流水线
cd 07_MVP_文献流水线
mkdir data, runs
```

## 0.3 建虚拟环境

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

命令行前面出现 `(.venv)` 就算成功。

## 0.4 安装依赖

```powershell
pip install requests lxml pymupdf pyyaml openai python-dotenv
```

## 0.5 验证

```powershell
python -c "import requests, lxml, fitz, yaml, openai; print('ok')"
```

输出 `ok` 就继续。

## 0.6 建 `.env`（放 API Key）

新建文件 `.env`，内容一行：

```
DEEPSEEK_API_KEY=sk-你的key
```

去 https://platform.deepseek.com 注册拿 key，充 10 块钱够跑几百篇。

> ⚠️ `.env` 不要发给别人、不要传到 GitHub。

---

# 阶段 1：让检索跑起来

## 1.1 先用浏览器看一眼接口（10 分钟，别跳过）

打开这个地址：

```
https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=oxytropis%20ochrocephala&format=json&pageSize=3&resultType=core
```

你会看到：`hitCount`、`resultList.result[]`，每条里有 `pmcid`、`doi`、`isOpenAccess`。
**记住这几个字段名**，后面代码全靠它。

## 1.2 建 `config.py`

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RUNS = ROOT / "runs"
DB = DATA / "litpipe.db"

DATA.mkdir(exist_ok=True)
RUNS.mkdir(exist_ok=True)

UA = {"User-Agent": "litpipe/0.1 (mailto:your_email@example.com)"}
RATE = 0.35          # 每次请求间隔秒数，Europe PMC 限 3 次/秒
```

> 把邮箱改成你自己的，这是礼貌也是防封。

## 1.3 建 `store.py`

```python
import json
import sqlite3
from config import DB


def conn():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS papers(
        id TEXT PRIMARY KEY, source TEXT, pmid TEXT, pmcid TEXT, doi TEXT,
        title TEXT, abstract TEXT, year INTEGER, journal TEXT, authors TEXT,
        pub_type TEXT, language TEXT, oa INTEGER, raw TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS cards(
        paper_id TEXT PRIMARY KEY, data TEXT, confidence TEXT, created TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS runs(
        run_id TEXT PRIMARY KEY, topic TEXT, query TEXT, counts TEXT,
        tokens INTEGER, cost REAL, started TEXT, finished TEXT)""")
    return c


def upsert_paper(c, p):
    c.execute("INSERT OR REPLACE INTO papers VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
        p["id"], p.get("source"), p.get("pmid"), p.get("pmcid"), p.get("doi"),
        p.get("title"), p.get("abstract"), p.get("year"), p.get("journal"),
        p.get("authors"), p.get("pub_type"), p.get("language"),
        1 if p.get("oa") else 0,
        json.dumps(p, ensure_ascii=False)))
    c.commit()
```

## 1.4 建 `topic.example.yaml`

```yaml
topic: 黄花棘豆抗锈
pico:
  population: "Oxytropis ochrocephala|黄花棘豆"
  intervention: "endophyte|Alternaria|内生真菌|链格孢"
  comparison: ""
  outcome: "rust|Uromyces|锈病"
years: 2010-2026
limit: 200
```

规则：同一个格子里的同义词用 `|` 分开；空格子直接留空。

## 1.5 建 `search.py`

```python
import argparse
import json
import time
import requests
import yaml

from config import UA, RATE
from store import conn, upsert_paper

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def build_query(t):
    parts = []
    for key in ("population", "intervention", "comparison", "outcome"):
        val = (t.get("pico") or {}).get(key) or ""
        if val.strip():
            ors = [x.strip() for x in val.split("|") if x.strip()]
            parts.append("(" + " OR ".join(ors) + ")")
    q = " AND ".join(parts)
    if t.get("years"):
        y0, y1 = str(t["years"]).split("-")
        q += f" AND (FIRST_PDATE:[{y0}-01-01 TO {y1}-12-31])"
    return q


def fetch_page(query, cursor, size=100):
    r = requests.get(EPMC, params={
        "query": query, "format": "json", "pageSize": size,
        "resultType": "core", "cursorMark": cursor,
    }, headers=UA, timeout=30)
    r.raise_for_status()
    return r.json()


def to_paper(it):
    journal = ((it.get("journalInfo") or {}).get("journal") or {}).get("title")
    pub_type = ((it.get("pubTypeList") or {}).get("pubType") or [None])[0]
    return {
        "id": it.get("id"),
        "source": it.get("source"),
        "pmid": it.get("pmid"),
        "pmcid": it.get("pmcid"),
        "doi": it.get("doi"),
        "title": it.get("title"),
        "abstract": it.get("abstractText"),
        "year": int(it["pubYear"]) if it.get("pubYear") else None,
        "journal": journal,
        "authors": it.get("authorString"),
        "pub_type": pub_type,
        "language": it.get("language"),
        "oa": it.get("isOpenAccess") == "Y",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    t = yaml.safe_load(open(args.topic, encoding="utf-8"))
    limit = args.limit or t.get("limit") or 200
    query = build_query(t)
    print("检索式：", query)

    c = conn()
    cursor, n = "*", 0
    while n < limit:
        data = fetch_page(query, cursor)
        items = (data.get("resultList") or {}).get("result") or []
        if not items:
            break
        for it in items:
            p = to_paper(it)
            if not p["id"]:
                continue
            upsert_paper(c, p)
            n += 1
            if n >= limit:
                break
        cursor = data.get("nextCursorMark")
        print(f"  已收 {n} 条")
        if not cursor or cursor == "*":
            break
        time.sleep(RATE)

    print(f"完成：{n} 条，已写入 data/litpipe.db")


if __name__ == "__main__":
    main()
```

## 1.6 跑第一次

```powershell
python search.py --topic topic.example.yaml --limit 50
```

**成功的样子**：先打印检索式，然后每页打印"已收 xx 条"，最后"完成：50 条"。

## 1.7 验证数据真的进去了

新建 `check.py`：

```python
from store import conn

c = conn()
print("papers =", c.execute("SELECT COUNT(*) FROM papers").fetchone()[0])
rows = c.execute("SELECT pmcid, doi, title FROM papers LIMIT 5").fetchall()
for r in rows:
    print(r)
```

```powershell
python check.py
```

**成功的样子**：`papers = 50` 左右，下面能打印出 5 条带 PMCID 的标题。

## 1.8 断点续跑验证

```powershell
python search.py --topic topic.example.yaml --limit 80
python check.py
```

条数应该涨到 80 左右，**不是重头再来**（因为 `INSERT OR REPLACE` 按 id 去重）。

> 卡住：如果报 429，把 `config.py` 里 `RATE` 改成 1.0；如果报 SSL，检查公司/校园网代理。

---

# 阶段 2：筛选

## 2.1 为什么要筛

检索会带进编辑评论、勘误、没摘要的条目。先用死规则筛一遍，别浪费模型钱。

## 2.2 建 `screen.py`

```python
import json
from config import RUNS
from store import conn

BAD_TYPES = {"editorial", "comment", "erratum", "correction", "retraction"}


def main():
    c = conn()
    rows = c.execute("""SELECT id, title, abstract, year, pub_type, pmcid, doi
                        FROM papers""").fetchall()
    keep, drop = [], []
    for r in rows:
        pid, title, abstract, year, ptype, pmcid, doi = r
        reason = None
        if not title:
            reason = "无标题"
        elif year and year < 2010:
            reason = "年份过早"
        elif (ptype or "").lower() in BAD_TYPES:
            reason = "非研究性条目"
        elif not abstract and not pmcid:
            reason = "无摘要且无全文"
        if reason:
            drop.append({"id": pid, "reason": reason})
        else:
            keep.append({"id": pid, "pmcid": pmcid, "doi": doi, "title": title})

    out = RUNS / "screened.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for x in keep:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")

    print(f"保留 {len(keep)} 条，排除 {len(drop)} 条 -> {out}")
    for d in drop[:10]:
        print("  排除", d["id"], d["reason"])


if __name__ == "__main__":
    main()
```

## 2.3 跑

```powershell
python screen.py
```

**成功的样子**：打印"保留 x 条，排除 y 条"，生成 `runs\screened.jsonl`。

## 2.4 人工抽检

用记事本打开 `screened.jsonl`，看 10 条标题：
- 有没有明显不相关的混进来？
- 有的话，回到 `topic.example.yaml` 补同义词或加排除词（Europe PMC 支持 `NOT`）。

---

# 阶段 3：抓全文与图

## 3.1 先确认一篇有图的文章长什么样

打开：

```
https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12196023/fullTextXML
```

搜 `<fig`，你会看到 `<label>Figure 1</label>`、`<caption>`、`<graphic ... xlink:href="xxx.jpg">`，还有一行 `<?cloudpmc-path blobs/...?>`。
**图片地址就是用这行拼出来的**：`https://cdn.ncbi.nlm.nih.gov/pmc/{cloudpmc-path}`。

## 3.2 建 `fetch.py`

```python
import json
import re
import time
from pathlib import Path

import requests
from lxml import etree

from config import DATA, UA, RATE
from store import conn

EPMC_XML = "https://www.ebi.ac.uk/europepmc/webservices/rest/{}/fullTextXML"
CDN = "https://cdn.ncbi.nlm.nih.gov/pmc/"


def text_of(node):
    return "".join(node.itertext()).strip()


def get_xml(pmcid):
    cache = DATA / "fulltext" / f"{pmcid}.xml"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and cache.stat().st_size > 1000:
        return cache.read_bytes()
    r = requests.get(EPMC_XML.format(pmcid), headers=UA, timeout=30)
    if r.status_code != 200:
        return None
    cache.write_bytes(r.content)
    time.sleep(RATE)
    return r.content


def parse_figs(xml_bytes, pmcid):
    root = etree.fromstring(xml_bytes)
    figs = []
    for fig in root.xpath("//*[local-name()='fig']"):
        label = ""
        lab = fig.xpath(".//*[local-name()='label']")
        if lab:
            label = text_of(lab[0])
        cap = ""
        caps = fig.xpath(".//*[local-name()='caption']")
        if caps:
            cap = text_of(caps[0])
        graphic = fig.xpath(".//*[local-name()='graphic']")
        if not graphic:
            continue
        href = graphic[0].get("{http://www.w3.org/1999/xlink}href", "")
        raw = etree.tostring(fig, encoding="unicode")
        cloud = re.search(r"cloudpmc-path\s+(\S+)", raw)
        url = CDN + cloud.group(1) if cloud else \
            f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/bin/{href}"
        figs.append({"label": label, "caption": cap, "href": href, "url": url})
    return figs


def link_paragraphs(root, figs):
    paras = [text_of(p) for p in root.xpath("//*[local-name()='p']")]
    for f in figs:
        num = re.search(r"(\d+)", f["label"])
        if not num:
            continue
        pat = re.compile(r"\bFig(?:ure)?\.?\s*" + num.group(1) + r"\b")
        for p in paras:
            if pat.search(p):
                f["linked_para"] = p[:300]
                break
    return figs


def download_image(fig, pmcid):
    folder = DATA / "figures" / pmcid
    folder.mkdir(parents=True, exist_ok=True)
    name = Path(fig["href"]).name or f"fig{len(fig)}.jpg"
    out = folder / name
    if out.exists() and out.stat().st_size > 1000:
        return str(out)
    try:
        r = requests.get(fig["url"], headers=UA, timeout=30)
        if r.status_code == 200 and len(r.content) > 1000:
            out.write_bytes(r.content)
            time.sleep(RATE)
            return str(out)
    except requests.RequestException:
        pass
    return None


def main():
    c = conn()
    rows = c.execute("SELECT pmcid FROM papers WHERE pmcid IS NOT NULL AND oa=1").fetchall()
    ok = 0
    for (pmcid,) in rows:
        xml = get_xml(pmcid)
        if not xml:
            print("跳过（拿不到全文）", pmcid)
            continue
        root = etree.fromstring(xml)
        figs = parse_figs(xml, pmcid)
        figs = link_paragraphs(root, figs)
        for f in figs:
            f["file"] = download_image(f, pmcid)
        idx = DATA / "figures" / pmcid / "index.json"
        idx.parent.mkdir(parents=True, exist_ok=True)
        idx.write_text(json.dumps(figs, ensure_ascii=False, indent=2), encoding="utf-8")
        ok += 1
        print(f"{pmcid}: {len(figs)} 张图")
    print(f"完成，{ok} 篇有全文")


if __name__ == "__main__":
    main()
```

## 3.3 跑

```powershell
python fetch.py
```

## 3.4 验证

```powershell
dir data\figures
```

挑一个 PMCID 目录打开 `index.json`，检查三件事：
1. `caption` 不是空的；
2. `file` 路径存在，图片能打开；
3. 至少一部分有 `linked_para`（正文里提到这张图的那句话）。

**验收线**：随机抽 10 篇，≥8 篇有图注，≥5 篇有引用句。

> 拿不到图：有些文章图不在 OA 包里，跳过即可，别硬爬。

---

# 阶段 4：抽卡片

## 4.1 先只调 1 篇

建 `prompts.py`：

```python
SYSTEM = """你是文献信息抽取员。只依据给定文本抽取，不许推测、不许补全。
只输出一个 JSON 对象，不要任何解释、不要 markdown 代码块。"""

USER = """请从下面这篇文献中抽取信息，输出 JSON，字段固定为：

{{
  "design": "研究设计（盆栽/田间/体外/动物实验/综述等）",
  "system": "研究对象与材料",
  "factor": "处理因素",
  "control": "对照设置",
  "n": "样本量，写数字或范围，未知填 null",
  "omics": ["涉及的组学层，如 16S, ITS, LC-MS, RNA-seq"],
  "outcome": "测了什么结局指标",
  "conclusion": "作者的主要结论，一句话",
  "limitation": "作者承认的局限，没有就填 null",
  "evidence": [{{"section": "results", "page": 7, "figure": "Fig.3",
                 "quote": "支撑这句话的原文片段，不超过 60 字"}}]
}}

规则：
1. 每条结论至少配 1 条 evidence；找不到就标 null，不要编。
2. page 不知道就填 null；有图号/表号必须填。
3. 只输出 JSON。

标题：{title}
期刊：{journal}（{year}）

摘要：
{abstract}

结果部分：
{results}
"""
```

建 `llm.py`：

```python
import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"),
                base_url="https://api.deepseek.com")


def ask_json(system, user, model="deepseek-chat"):
    resp = client.chat.completions.create(
        model=model, temperature=0,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        max_tokens=2000,
    )
    txt = resp.choices[0].message.content.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        txt = txt[txt.find("{"):]
    return json.loads(txt), resp.usage.total_tokens
```

建 `card.py`：

```python
import json
import time
from datetime import datetime
from lxml import etree

from config import DATA
from llm import ask_json
from prompts import SYSTEM, USER
from store import conn

PRICE_PER_1K = 0.002      # 按你实际模型的单价改，单位：元/千 token


def text_of(node):
    return "".join(node.itertext()).strip()


def results_text(root, limit=7000):
    for sec in root.xpath("//*[local-name()='sec']"):
        t = sec.xpath(".//*[local-name()='title']")
        if t and "result" in text_of(t[0]).lower():
            return " ".join(text_of(p) for p in sec.xpath(".//*[local-name()='p']"))[:limit]
    body = root.xpath("//*[local-name()='body']")
    if body:
        return " ".join(text_of(p) for p in body[0].xpath(".//*[local-name()='p']"))[:limit]
    return ""


def main(only=None, limit=None):
    c = conn()
    rows = c.execute("""SELECT id, pmcid, doi, title, journal, year, abstract
                        FROM papers WHERE pmcid IS NOT NULL AND oa=1""").fetchall()
    done = tokens = 0
    for pid, pmcid, doi, title, journal, year, abstract in rows:
        if only and pid != only:
            continue
        if limit and done >= limit:
            break
        xml_path = DATA / "fulltext" / f"{pmcid}.xml"
        if not xml_path.exists():
            continue
        root = etree.fromstring(xml_path.read_bytes())
        prompt = USER.format(title=title or "", journal=journal or "",
                             year=year or "", abstract=(abstract or "")[:1500],
                             results=results_text(root))
        try:
            data, tk = ask_json(SYSTEM, prompt)
            tokens += tk
        except Exception as e:
            print("抽取失败", pid, e)
            continue
        ev = data.get("evidence") or []
        conf = "high" if ev and data.get("conclusion") else "low"
        data["paper"] = {"id": pid, "doi": doi, "title": title,
                         "journal": journal, "year": year}
        out = DATA / "cards" / f"{pid}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        c.execute("INSERT OR REPLACE INTO cards VALUES(?,?,?,?)",
                  (pid, json.dumps(data, ensure_ascii=False), conf,
                   datetime.now().isoformat(timespec="seconds")))
        c.commit()
        done += 1
        print(f"[{done}] {pid} {conf} {data.get('conclusion')}")
        time.sleep(0.5)
    print(f"完成 {done} 篇，tokens={tokens}，约 {tokens/1000*PRICE_PER_1K:.2f} 元")


if __name__ == "__main__":
    import sys
    only = sys.argv[1] if len(sys.argv) > 1 else None
    main(only=only)
```

## 4.2 单篇调试

先挑一个 PMCID，把 `card.py` 里 `main(only=...)` 用上，或者直接：

```powershell
python -c "import card; card.main(only='40572460')"
```

打开 `data\cards\40572460.json`，逐项检查：
- `design` 对不对？
- `conclusion` 是不是作者的原话，不是你的理解？
- `evidence` 里有没有图号/页码？

**不满意就改 `prompts.py`，只改这一篇，改到满意为止。** 这一步花 1–2 天很正常。

## 4.3 小批量

```powershell
python -c "import card; card.main(limit=5)"
```

看 5 篇里几篇字段齐全。低于 4 篇就回去改提示词。

## 4.4 全量

```powershell
python -c "import card; card.main(limit=50)"
```

## 4.5 抽检

随机挑 5 张卡，回原文核对 `conclusion` 和 `evidence`。
**判断标准**：卡片说的话，原文那一页/那张图是否真的支持。错 2 条以上，说明提示词还得改。

---

# 阶段 5：导出简报

## 5.1 建 `export.py`

```python
import json
from datetime import date
from config import RUNS
from store import conn


def load_cards():
    c = conn()
    rows = c.execute("SELECT data, confidence FROM cards").fetchall()
    return [(json.loads(d), conf) for d, conf in rows]


def card_md(card, conf):
    p = card.get("paper", {})
    ref = f"[{p.get('doi') or p.get('id')}]"
    ev = card.get("evidence") or []
    ev_txt = "；".join(
        f"{e.get('section','')} p.{e.get('page','?')} {e.get('figure','')}".strip()
        for e in ev) or "无定位"
    return f"""### {p.get('title','')}

- 期刊/年份：{p.get('journal','')} {p.get('year','')}
- 设计：{card.get('design')}；系统：{card.get('system')}
- 因素/对照：{card.get('factor')} / {card.get('control')}；n={card.get('n')}
- 组学：{', '.join(card.get('omics') or [])}
- 结局：{card.get('outcome')}
- 结论：{card.get('conclusion')}
- 局限：{card.get('limitation')}
- 证据：{ev_txt} {ref}
"""


def main():
    cards = load_cards()
    good = [(c, f) for c, f in cards if f != "low"]
    low = [(c, f) for c, f in cards if f == "low"]
    md = [f"# 文献证据简报\n", f"生成日期：{date.today()}\n",
          f"共 {len(cards)} 篇；可直接引用 {len(good)} 篇；待核 {len(low)} 篇\n"]
    md.append("\n## 一、可直接引用\n")
    for c, f in good:
        md.append(card_md(c, f))
    md.append("\n## 二、待核（证据不足，别当结论用）\n")
    for c, f in low:
        md.append(card_md(c, f))
    out = RUNS / "brief.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print("已生成", out)


if __name__ == "__main__":
    main()
```

## 5.2 跑

```powershell
python export.py
```

打开 `runs\brief.md`，检查：
- 每条结论后面有没有 `p.?` 或图号；
- “待核”区是不是单独列出来了。

---

# 阶段 6：批量与稳定性

## 6.1 一条命令跑全流程

建 `run_all.py`：

```python
import subprocess
import sys

steps = [
    ["python", "search.py", "--topic", "topic.example.yaml", "--limit", "100"],
    ["python", "screen.py"],
    ["python", "fetch.py"],
    ["python", "-c", "import card; card.main(limit=100)"],
    ["python", "export.py"],
]
for s in steps:
    print("\n>>>", " ".join(s))
    r = subprocess.run(s)
    if r.returncode != 0:
        print("!! 这一步失败，停在这里")
        sys.exit(1)
```

```powershell
python run_all.py
```

## 6.2 断点续跑

- 检索：按 id 去重，重跑不重复
- 全文：`data/fulltext` 有缓存，不重下
- 图：文件存在就跳过
- 卡片：已有 `cards\<id>.json` 的会重复抽取，**改一下 `card.py`，开头加**：

```python
if (DATA / "cards" / f"{pid}.json").exists():
    continue
```

## 6.3 日志

```powershell
python run_all.py *> runs\run.log
```

出问题看最后 20 行：

```powershell
Get-Content runs\run.log -Tail 20
```

## 6.4 压测

```powershell
python search.py --topic topic.example.yaml --limit 200
python -c "import card; card.main(limit=100)"
```

记录：跑完多久、花了多少 token、多少篇 `low`。

---

# 阶段 7：套界面（可砍）

## 7.1 装 Streamlit

```powershell
pip install streamlit
```

## 7.2 建 `app.py`

```python
import streamlit as st
import subprocess

st.title("文献流水线")
topic = st.text_input("研究方向", "黄花棘豆抗锈")
limit = st.number_input("最多抓多少篇", 20, 500, 100)

if st.button("开始跑"):
    with st.spinner("检索 + 筛选 + 抓全文…"):
        subprocess.run(["python", "search.py", "--topic", "topic.example.yaml",
                        "--limit", str(limit)], check=False)
        subprocess.run(["python", "screen.py"], check=False)
        subprocess.run(["python", "fetch.py"], check=False)
    st.success("跑完了，去 runs 目录看结果")

st.divider()
try:
    st.markdown(open("runs/brief.md", encoding="utf-8").read())
except FileNotFoundError:
    st.info("还没有简报，先跑一次")
```

## 7.3 启动

```powershell
streamlit run app.py
```

浏览器会自动打开。**界面只是壳，别在这上面花超过 2 天。**

---

# 阶段 8：交卷

## 8.1 三个方向各跑一遍

复制三份 `topic.yaml`：`topic.oxytropis.yaml`、`topic.barley.yaml`、`topic.silage.yaml`，各跑：

```powershell
python search.py --topic topic.oxytropis.yaml --limit 200
python screen.py
python fetch.py
python -c "import card; card.main(limit=100)"
python export.py
```

## 8.2 记录一张实测表

| 方向 | 检索 | 筛选后 | 有全文 | 卡片 | 待核 | 成本 | 耗时 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 黄花棘豆抗锈 | | | | | | | |
| 大麦内生菌 | | | | | | | |
| 青贮品质 | | | | | | | |

## 8.3 截图与录屏

- 检索式那一行
- 卡片 JSON 里的 evidence
- `figures` 目录里的图
- brief.md 的效果
- 3 分钟录屏：填方向 → 跑 → 出简报

---

# 附录：常见报错对照表

| 报错 | 原因 | 解法 |
| --- | --- | --- |
| `ModuleNotFoundError: requests` | 没激活虚拟环境 | `.\.venv\Scripts\Activate.ps1` |
| `429 Too Many Requests` | 请求太快 | `config.py` 里 `RATE` 改 1.0 |
| `JSONDecodeError` | 模型返回带 ``` | 已在 `llm.py` 里剥掉；仍报就把 `max_tokens` 调大 |
| `KeyError: 'resultList'` | 检索式语法错，返回空 | 先用浏览器打开同一 URL 看返回 |
| 图片 404 | 该文图不在 OA 包 | 跳过，只留图注 |
| `UnicodeEncodeError` | 控制台编码 | 文件全部 `encoding="utf-8"`，已处理 |
| 卡片全是 `low` | 模型没给 evidence | 提示词里把 evidence 要求放到最前面，并给一个例子 |

---

# 每天收工前问自己三句

1. 今天跑的命令，明天原样还能跑通吗？
2. 今天新增的结论，能指到原文哪一页/哪张图吗？
3. 今天的进度和坑，写进 `runs\run.log` 了吗？

---

*版本：2026-11-18。按这份做，20 天能跑通；卡在某一步，把报错原文发我。*

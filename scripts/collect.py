#!/usr/bin/env python3
"""采集真实文献数据：Europe PMC 检索 + OA 全文图注。"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
UA = {"User-Agent": "LitRadar/0.1 (mailto:pan@example.com)"}

QUERIES = [
    '(coumarin OR coumarins) AND (rhizosphere OR "root exudate" OR "root exudates")',
    '(coumarin OR coumarins) AND (microbiome OR microbiota OR "microbial community")',
    '(scopoletin OR fraxetin OR daphnetin OR esculetin) AND (rhizosphere OR microbiome OR "root exudate")',
    'coumarin AND "iron deficiency" AND (plant OR Arabidopsis)',
]

FIG_RE = re.compile(r"<fig\b[^>]*>.*?</fig>", re.S)
LABEL_RE = re.compile(r"<label[^>]*>(.*?)</label>", re.S)
CAP_RE = re.compile(r"<caption[^>]*>(.*?)</caption>", re.S)
GRAPH_RE = re.compile(r"<graphic[^>]*?xlink:href=\"([^\"]+)\"[^>]*>(.*?)</graphic>", re.S)
CLOUD_RE = re.compile(r"cloudpmc-path\s+(\S+)")
TAG_RE = re.compile(r"<[^>]+>")


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def search(q, size=100):
    url = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
           + urllib.parse.urlencode({"query": q, "format": "json",
                                     "pageSize": size, "resultType": "core"}))
    return json.loads(fetch(url))


def clean(s):
    s = TAG_RE.sub("", s or "")
    return re.sub(r"\s+", " ", s).strip()


def to_paper(it):
    j = ((it.get("journalInfo") or {}).get("journal") or {})
    return {
        "id": it.get("id"),
        "pmid": it.get("pmid"),
        "pmcid": it.get("pmcid"),
        "doi": it.get("doi"),
        "title": clean(it.get("title")),
        "abstract": clean(it.get("abstractText")),
        "year": int(it["pubYear"]) if it.get("pubYear") else None,
        "journal": j.get("title") or j.get("medlineAbbreviation"),
        "authors": it.get("authorString"),
        "oa": it.get("isOpenAccess") == "Y",
        "cited": it.get("citedByCount") or 0,
    }


def figures(pmcid):
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
    try:
        xml = fetch(url).decode("utf-8", "ignore")
    except Exception:
        return None
    out = []
    for fig in FIG_RE.findall(xml):
        label = LABEL_RE.search(fig)
        cap = CAP_RE.search(fig)
        graph = GRAPH_RE.search(fig)
        if not graph:
            continue
        href = graph.group(1)
        cloud = CLOUD_RE.search(fig)
        img = ("https://cdn.ncbi.nlm.nih.gov/pmc/" + cloud.group(1)) if cloud else \
              f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/bin/{href}"
        out.append({
            "label": clean(label.group(1)) if label else "",
            "caption": clean(cap.group(1)) if cap else "",
            "href": href,
            "url": img,
        })
    return out


def main():
    papers, seen = [], set()
    for q in QUERIES:
        try:
            data = search(q)
        except Exception as e:
            print("检索失败", q, e)
            continue
        print(f"{q[:60]}... hit={data.get('hitCount')}")
        for it in (data.get("resultList") or {}).get("result") or []:
            p = to_paper(it)
            key = p["doi"] or p["id"]
            if not key or key in seen:
                continue
            if (p["year"] or 0) < 2012:
                continue
            seen.add(key)
            papers.append(p)
        time.sleep(0.4)

    papers.sort(key=lambda p: (-(p["year"] or 0), -p["cited"]))
    with open(os.path.join(DATA, "papers.json"), "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=1)
    print("唯一文献", len(papers), "其中有全文", sum(1 for p in papers if p["pmcid"] and p["oa"]))

    figdir = os.path.join(DATA, "figures")
    ok = 0
    for p in papers:
        if not (p["pmcid"] and p["oa"]):
            continue
        if ok >= 45:
            break
        figs = figures(p["pmcid"])
        if figs is None:
            continue
        p["figures"] = figs
        if figs:
            with open(os.path.join(figdir, p["pmcid"] + ".json"), "w", encoding="utf-8") as f:
                json.dump(figs, f, ensure_ascii=False, indent=1)
            ok += 1
            print(f"{p['pmcid']}: {len(figs)} 图")
        time.sleep(0.4)

    with open(os.path.join(DATA, "papers.json"), "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=1)
    total_figs = sum(len(p.get("figures") or []) for p in papers)
    stats = {
        "papers": len(papers),
        "with_fulltext": sum(1 for p in papers if p["pmcid"] and p["oa"]),
        "with_figures": ok,
        "figures": total_figs,
        "years": [min(p["year"] for p in papers if p["year"]), max(p["year"] for p in papers if p["year"])],
    }
    with open(os.path.join(DATA, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)
    print(stats)


if __name__ == "__main__":
    main()

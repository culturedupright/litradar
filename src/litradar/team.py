"""课题组实力评估：按基金评审常用的五个维度自评，1–5 级，带锚点。

只做“能不能接住这个选题”的粗筛，不替代同行评议；每项都要求使用者自己填，
插件不编机构数据。评分与短板结论写进开题报告的“可行性分析”一节。
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import HOME

PATH = Path(HOME / "team.json")

DIMENSIONS: tuple[dict, ...] = (
    {"key": "pi", "label": "PI 学术资本", "weight": 0.30,
     "hint": "通讯作者论文、h 指数、代表作层级",
     "anchors": {1: "无相关通讯作者论文", 3: "有领域内常规期刊通讯论文", 5: "有领域顶刊/高被引代表作"}},
    {"key": "platform", "label": "平台与条件", "weight": 0.20,
     "hint": "重点实验室、关键仪器、算力/测序/表征条件",
     "anchors": {1: "依赖外部平台", 3: "常用设备可满足", 5: "国家级平台且关键设备自持"}},
    {"key": "foundation", "label": "前期积累", "weight": 0.20,
     "hint": "预实验、已有数据、专利、合作基础",
     "anchors": {1: "从零开始", 3: "有初步数据", 5: "有成型预实验/数据/专利"}},
    {"key": "team", "label": "团队梯队", "weight": 0.15,
     "hint": "博士生/博后/技术员配置与分工覆盖",
     "anchors": {1: "单人作战", 3: "2–3 人可分工", 5: "完整梯队且有技术支撑"}},
    {"key": "funding", "label": "经费与项目", "weight": 0.15,
     "hint": "在研国家/省部级项目与可支配经费",
     "anchors": {1: "无在研经费", 3: "有校级/小额度支持", 5: "有国家级在研项目"}},
)

BANDS = ((4.2, "强", "条件基本够，可直接立项"), (3.0, "中", "能做，但需在方案里写清补短板"),
         (0.0, "弱", "建议先合作或缩小目标，别硬上"))


def defaults() -> dict:
    return {d["key"]: {"level": 3, "note": ""} for d in DIMENSIONS}


def load() -> dict:
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        data = {}
    profile = defaults()
    for key, value in (data or {}).items():
        if key in profile and isinstance(value, dict):
            profile[key]["level"] = max(1, min(5, int(value.get("level", 3))))

            profile[key]["note"] = str(value.get("note") or "")
    return profile


def save(profile: dict) -> dict:
    clean = defaults()
    for key in clean:
        item = (profile or {}).get(key) or {}
        clean[key]["level"] = max(1, min(5, int(item.get("level", 3))))
        clean[key]["note"] = str(item.get("note") or "")[:300]
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return clean


def evaluate(profile: dict | None = None) -> dict:
    profile = profile or load()
    score = 0.0
    rows = []
    for dim in DIMENSIONS:
        level = max(1, min(5, int((profile.get(dim["key"]) or {}).get("level", 3))))
        score += level * dim["weight"]
        rows.append({**dim, "level": level,
                     "note": str((profile.get(dim["key"]) or {}).get("note") or "")})
    band, advice = next((b, a) for threshold, b, a in BANDS if score >= threshold)
    gaps = [row["label"] for row in rows if row["level"] <= 2]
    return {"score": round(score, 2), "band": band, "advice": advice,
            "gaps": gaps, "rows": rows}


def markdown_block(profile: dict | None = None) -> list[str]:
    result = evaluate(profile)
    lines = ["### 课题组条件自评", "",
             f"- 综合得分：**{result['score']} / 5**（{result['band']}）——{result['advice']}",
             "- 维度明细（1–5 级，权重为评审常用口径，可按本单位要求调整）：", "",
             "| 维度 | 权重 | 评级 | 说明 |", "| --- | --- | --- | --- |"]
    for row in result["rows"]:
        note = row["note"] or row["hint"]
        lines.append(f"| {row['label']} | {row['weight']:.2f} | {row['level']} | {note} |")
    if result["gaps"]:
        lines += ["", f"- 短板：{'、'.join(result['gaps'])}。方案里要写明补法（合作、共享平台、缩小目标）。"]
    lines += ["", "> 自评只用于判断选题是否匹配现有条件，不代表同行评议结论。"]
    return lines

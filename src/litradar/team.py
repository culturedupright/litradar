"""课题组条件：按基金评审常用的五个维度做条件核对，并把实验类型/经费/周期并进来。

为什么不用滑杆：
- 滑杆让使用者自己定义“3 级”是什么，同一个人两次打分都可能不一致；
- 评审专家看的是可核对的事实（通讯作者层级、平台层级、在研项目），不是感觉。

所以界面默认走“快速填写”：填单位、申请人身份、通讯作者与职称、课题组人数、在研项目、
单位平台层级，由规则推算出五维等级，再允许逐项改成更贴近实际的下拉档位。
每档都写死判据（criteria），报告里原样引用，避免自评变成拍脑袋。

五维与权重参考国家自然科学基金/国家重点研发计划通讯评议常用的
“负责人学术水平—研究平台—前期基础—队伍组成—经费保障”结构，权重可按本单位口径调整。
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import HOME

PATH = Path(HOME / "team.json")

ROLES = ["本科生", "硕士生", "博士生", "博士后", "青年教师", "课题负责人（PI）"]
ORGS = ["普通高校院系", "省部级重点实验室/平台", "国家级平台/重点实验室", "全国重点实验室"]
AUTHOR_TITLES = ["无通讯作者论文", "讲师/中级", "副教授/副高", "教授/正高", "国家级人才/领域领军"]
GROUP_SIZES = ["1 人", "2–3 人", "4–8 人", "9 人以上", "完整梯队（含专职技术员）"]
PROJECTS = ["无在研项目", "校级/院级项目", "省部级项目", "国家级项目", "国家级重大/重点项目"]

CONDITIONS: tuple[dict, ...] = (
    {"key": "experiment", "label": "实验类型",
     "options": ["湿实验为主", "干实验为主", "干湿结合", "理论仿真与建模"]},
    {"key": "budget", "label": "可支配经费量级",
     "options": ["5 万以内", "5–20 万", "20–100 万", "100 万以上"]},
    {"key": "period", "label": "可投入周期",
     "options": ["3 个月", "6 个月", "1 年", "2 年以上"]},
    {"key": "wet", "label": "湿实验条件",
     "options": ["具备湿实验条件", "需外协或合作", "不做湿实验"]},
)

DIMENSIONS: tuple[dict, ...] = (
    {"key": "pi", "label": "负责人学术水平", "label_en": "PI academic standing", "weight": 0.30,
     "hint": "看通讯作者论文与代表作层级，不看头衔数量",
     "options": [
         {"level": 1, "label": "无相关通讯作者论文", "criteria": "仅有参与作者论文"},
         {"level": 2, "label": "普通期刊通讯作者", "criteria": "有同领域常规期刊通讯论文"},
         {"level": 3, "label": "领域主流期刊通讯作者", "criteria": "有领域主流期刊通讯论文，h 指数中等"},
         {"level": 4, "label": "领域顶刊/高被引通讯作者", "criteria": "有顶刊或高被引通讯论文"},
         {"level": 5, "label": "国家级人才/领域领军", "criteria": "多篇顶刊通讯，主持国家级重大项目"},
     ]},
    {"key": "platform", "label": "研究平台与条件", "label_en": "Platform and facilities", "weight": 0.20,
     "hint": "关键设备能不能自持，决定要不要外协",
     "options": [
         {"level": 1, "label": "依赖外部平台", "criteria": "关键设备全部外协"},
         {"level": 2, "label": "常规设备可满足部分", "criteria": "本单位只能做常规制备/测试"},
         {"level": 3, "label": "省部级平台，常用设备齐全", "criteria": "常用表征与制备设备自持"},
         {"level": 4, "label": "国家级平台，关键设备自持", "criteria": "关键设备与专用线站可用"},
         {"level": 5, "label": "全国重点实验室级平台", "criteria": "国家级平台＋专属装置/算力/试验基地"},
     ]},
    {"key": "foundation", "label": "前期研究基础", "label_en": "Preliminary foundation", "weight": 0.20,
     "hint": "预实验、数据、专利、方法积累",
     "options": [
         {"level": 1, "label": "从零开始", "criteria": "没有相关数据或预实验"},
         {"level": 2, "label": "有课程/文献层面的准备", "criteria": "读过文献、有初步方案"},
         {"level": 3, "label": "有初步预实验数据", "criteria": "已有小样本预实验或初步结果"},
         {"level": 4, "label": "有成型预实验/专利/方法", "criteria": "预实验成体系，或已有专利/方法学成果"},
         {"level": 5, "label": "有连续项目与数据体系", "criteria": "多轮项目积累，数据与平台可持续"},
     ]},
    {"key": "team", "label": "队伍组成", "label_en": "Team composition", "weight": 0.15,
     "hint": "能不能覆盖设计、执行、分析三类分工",
     "options": [
         {"level": 1, "label": "单人作战", "criteria": "设计、执行、分析都由一人承担"},
         {"level": 2, "label": "2–3 人可分工", "criteria": "能拆出执行与分析"},
         {"level": 3, "label": "4–8 人小组", "criteria": "有研究生参与，分工基本覆盖"},
         {"level": 4, "label": "博士/博后＋技术支撑", "criteria": "有高级研究人员与专职技术员"},
         {"level": 5, "label": "完整梯队", "criteria": "PI＋博后＋博士＋技术员，分工与备份齐全"},
     ]},
    {"key": "funding", "label": "经费与项目保障", "label_en": "Funding and projects", "weight": 0.15,
     "hint": "在研项目层级与可支配额度",
     "options": [
         {"level": 1, "label": "无在研经费", "criteria": "只能靠自筹"},
         {"level": 2, "label": "校级/院级小额支持", "criteria": "额度只够预实验"},
         {"level": 3, "label": "省部级在研项目", "criteria": "可覆盖主体实验"},
         {"level": 4, "label": "国家级在研项目", "criteria": "面上/重点级，可覆盖外协"},
         {"level": 5, "label": "国家级重大/多源经费", "criteria": "重大/重点＋横向等多源保障"},
     ]},
)

BANDS = ((4.2, "强", "条件基本够，可直接立项"), (3.0, "中", "能做，但需在方案里写清补短板"),
         (0.0, "弱", "建议先合作或缩小目标，别硬上"))

TITLE_LEVEL = {"无通讯作者论文": 1, "讲师/中级": 2, "副教授/副高": 3,
               "教授/正高": 4, "国家级人才/领域领军": 5}
ORG_LEVEL = {"普通高校院系": 2, "省部级重点实验室/平台": 3,
             "国家级平台/重点实验室": 4, "全国重点实验室": 5}
GROUP_LEVEL = {"1 人": 1, "2–3 人": 2, "4–8 人": 3, "9 人以上": 4,
               "完整梯队（含专职技术员）": 5}
PROJECT_LEVEL = {"无在研项目": 1, "校级/院级项目": 2, "省部级项目": 3,
                 "国家级项目": 4, "国家级重大/重点项目": 5}

DEFAULTS_IDENTITY = {"unit": "", "role": "博士生", "org": "省部级重点实验室/平台",
                     "author": "", "author_title": "教授/正高",
                     "group_size": "4–8 人", "project": "省部级项目"}
DEFAULTS_CONDITIONS = {"experiment": "干湿结合", "budget": "5–20 万",
                       "period": "1 年", "wet": "具备湿实验条件"}


def _level_in(key: str, value: object, default: int = 3) -> int:
    try:
        return max(1, min(5, int(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def defaults() -> dict:
    base = {"mode": "quick", "identity": dict(DEFAULTS_IDENTITY),
            "dims": {d["key"]: {"level": 3, "source": "auto", "note": ""}
                     for d in DIMENSIONS},
            "conditions": dict(DEFAULTS_CONDITIONS)}
    base["dims"].update(derive(base["identity"]))
    return base


def derive(identity: dict) -> dict:
    """按填写的单位/职称/人数/项目推算五维等级；只做保守映射，不夸大。"""
    identity = {**DEFAULTS_IDENTITY, **(identity or {})}
    pi = TITLE_LEVEL.get(identity.get("author_title"), 3)
    platform = ORG_LEVEL.get(identity.get("org"), 3)
    foundation = PROJECT_LEVEL.get(identity.get("project"), 3)
    team = GROUP_LEVEL.get(identity.get("group_size"), 3)
    funding = PROJECT_LEVEL.get(identity.get("project"), 3)
    if identity.get("role") == "本科生":
        foundation = min(foundation, 3)
        team = min(team, 4)
    elif identity.get("role") == "硕士生":
        foundation = min(foundation, 4)
    return {key: {"level": level, "source": "auto", "note": ""}
            for key, level in (("pi", pi), ("platform", platform),
                               ("foundation", foundation), ("team", team),
                               ("funding", funding))}


def _merge(raw: dict | None) -> dict:
    data = defaults()
    raw = raw or {}
    if not isinstance(raw, dict):
        return data
    if raw.get("mode") in ("quick", "expert"):
        data["mode"] = raw["mode"]
    identity = raw.get("identity") if isinstance(raw.get("identity"), dict) else {}
    for key, value in identity.items():
        if key in data["identity"] and isinstance(value, str):
            data["identity"][key] = value[:80]
    conditions = raw.get("conditions") if isinstance(raw.get("conditions"), dict) else {}
    for key, value in conditions.items():
        if key in data["conditions"] and isinstance(value, str):
            data["conditions"][key] = value[:40]
    dims = raw.get("dims") if isinstance(raw.get("dims"), dict) else None
    legacy = not dims and any(isinstance(raw.get(k), dict) for k in data["dims"])
    source = dims or {k: raw.get(k) for k in data["dims"]}
    for key, value in (source or {}).items():
        if key not in data["dims"] or not isinstance(value, dict):
            continue
        data["dims"][key]["level"] = _level_in(key, value.get("level"))
        data["dims"][key]["source"] = "auto" if (value.get("source") == "auto" or legacy) else "manual"
        data["dims"][key]["note"] = str(value.get("note") or "")[:300]
    return data


def load() -> dict:
    try:
        return _merge(json.loads(PATH.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001
        return defaults()


def save(profile: dict) -> dict:
    clean = _merge(profile)
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return clean


def quick_derive(profile: dict) -> dict:
    """只改“自动推算”的维度，手动改过的档位保留。"""
    profile = _merge(profile)
    for key, item in derive(profile["identity"]).items():
        if profile["dims"][key].get("source") == "auto":
            profile["dims"][key]["level"] = item["level"]
            profile["dims"][key]["note"] = ""
    return profile


def conditions(profile: dict | None = None) -> dict:
    return _merge(profile)["conditions"]


def _option(dim: dict, level: int) -> dict:
    return next((o for o in dim["options"] if o["level"] == level), dim["options"][2])


def evaluate(profile: dict | None = None) -> dict:
    profile = _merge(profile)
    score = 0.0
    rows = []
    for dim in DIMENSIONS:
        item = profile["dims"][dim["key"]]
        level = _level_in(dim["key"], item.get("level"))
        option = _option(dim, level)
        score += level * dim["weight"]
        rows.append({**{k: dim[k] for k in ("key", "label", "label_en", "weight", "hint")},
                     "level": level, "option": option["label"],
                     "criteria": option["criteria"], "source": item.get("source", "manual"),
                     "note": str(item.get("note") or "")})
    band, advice = next((b, a) for threshold, b, a in BANDS if score >= threshold + 1e-9)
    gaps = [row["label"] for row in rows if row["level"] <= 2]
    return {"score": round(score, 2), "band": band, "advice": advice,
            "gaps": gaps, "rows": rows, "identity": profile["identity"],
            "conditions": profile["conditions"], "mode": profile["mode"]}


def schema() -> dict:
    """给界面渲染表单：快速填写项、五维档位、研究条件选项。"""
    return {
        "identity": [
            {"key": "unit", "label": "单位/院系", "type": "text",
             "placeholder": "例：兰州大学草地农业科技学院"},
            {"key": "role", "label": "申请人身份", "type": "select", "options": ROLES},
            {"key": "org", "label": "单位平台层级", "type": "select", "options": ORGS},
            {"key": "author", "label": "通讯作者", "type": "text", "placeholder": "姓名"},
            {"key": "author_title", "label": "通讯作者职称/层级", "type": "select",
             "options": AUTHOR_TITLES},
            {"key": "group_size", "label": "课题组人数", "type": "select", "options": GROUP_SIZES},
            {"key": "project", "label": "在研项目层级", "type": "select", "options": PROJECTS},
        ],
        "conditions": [{"key": c["key"], "label": c["label"], "options": c["options"]}
                       for c in CONDITIONS],
        "dimensions": [{"key": d["key"], "label": d["label"], "label_en": d["label_en"],
                        "weight": d["weight"], "hint": d["hint"],
                        "options": [{"level": o["level"], "label": o["label"],
                                     "criteria": o["criteria"]} for o in d["options"]]}
                       for d in DIMENSIONS],
    }


def markdown_block(profile: dict | None = None) -> list[str]:
    result = evaluate(profile)
    identity = result["identity"]
    lines = ["### 课题组条件自评", "",
             f"- 综合得分：**{result['score']} / 5**（{result['band']}）——{result['advice']}",
             f"- 单位：{identity.get('unit') or '待申请人补充'}；"
             f"申请人身份：{identity.get('role')}；"
             f"通讯作者：{(identity.get('author') or '待补')}（{identity.get('author_title')}）；"
             f"课题组规模：{identity.get('group_size')}；在研项目：{identity.get('project')}",
             "- 五维评级（1–5 级；权重按通讯评议常用结构，可按本单位口径调整）：", "",
             "| 维度 | 权重 | 评级 | 档位判据 | 来源 |", "| --- | --- | --- | --- | --- |"]
    for row in result["rows"]:
        origin = "自动推算" if row["source"] == "auto" else "手工填写"
        lines.append(f"| {row['label']} | {row['weight']:.2f} | {row['level']} | "
                     f"{row['option']}（{row['criteria']}） | {origin} |")
    cond = result["conditions"]
    lines += ["", "研究条件（用于判断方案规模）：", "",
              "| 条件 | 取值 |", "| --- | --- |"]
    for spec in CONDITIONS:
        lines.append(f"| {spec['label']} | {cond.get(spec['key'], '')} |")
    if result["gaps"]:
        lines += ["", f"- 短板：{'、'.join(result['gaps'])}。"
                      "方案里要写明补法（合作、共享平台、缩小目标或分期实施）。"]
    lines += ["", "> 自评只用于判断选题是否匹配现有条件，不代表同行评议结论。"]
    return lines

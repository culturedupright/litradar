"""课题组与研究条件：按基金评审常用的五个维度核对条件，并把研究类型、资源、规范并进来。

界面走“可核对事实 → 规则推算 → 带判据档位”三段：单位、申请人身份、通讯作者、代表作、
课题组规模、在研项目这些事实先填，五维等级由固定规则推算；需要更贴实际时逐项改档位。
每档写死判据，报告里原样引用，避免自评变成拍脑袋。

五维结构参考国家自然科学基金/国家重点研发计划通讯评议常用的
“负责人学术水平—研究平台—前期基础—队伍组成—经费保障”，权重可按本单位口径调整。
成果评价采用 DORA（San Francisco Declaration on Research Assessment）原则：
以代表作、具体贡献与研究质量为主，不把期刊影响因子、h-index、引用数当作单个替代指标。
研究规范按研究类型选择：动物实验 ARRIVE 2.0、临床试验 CONSORT、系统综述 PRISMA、
观察性研究 STROBE、预测模型 TRIPOD；数据管理按 FAIR 原则与数据管理计划（DMP）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import HOME

PATH = Path(HOME / "team.json")

ROLES = ["本科生", "硕士生", "博士生", "博士后", "青年教师", "课题负责人（PI）"]
ORGS = ["普通高校院系", "省部级重点实验室/平台", "国家级平台/重点实验室", "全国重点实验室"]
AUTHOR_TITLES = ["无通讯作者论文", "讲师/中级", "副教授/副高", "教授/正高", "国家级人才/领域领军"]
GROUP_SIZES = ["1 人", "2–3 人", "4–8 人", "9 人以上", "完整梯队（含专职技术员）"]
PROJECTS = ["无在研项目", "校级/院级项目", "省部级项目", "国家级项目", "国家级重大/重点项目"]

CONDITIONS: tuple[dict, ...] = (
    {"key": "experiment", "label": "研究类型", "group": "研究方式",
     "options": ["理论/计算研究", "湿实验", "干湿结合", "临床/人群研究",
                 "田野调查/社会调查", "文本/档案/历史研究"]},
    {"key": "data_source", "label": "数据来源", "group": "研究方式",
     "options": ["自建一手数据", "共享数据库", "公开数据", "多源整合", "待定"]},
    {"key": "platform_access", "label": "平台使用方式", "group": "资源与周期",
     "options": ["自有设备/平台", "校内共享平台", "校外合作/外协", "纯计算资源"]},
    {"key": "budget", "label": "可支配经费量级", "group": "资源与周期",
     "options": ["5 万以内", "5–20 万", "20–100 万", "100 万以上"]},
    {"key": "period", "label": "可投入周期", "group": "资源与周期",
     "options": ["3 个月", "6 个月", "1 年", "2 年以上"]},
    {"key": "wet", "label": "湿实验条件", "group": "资源与周期",
     "options": ["具备湿实验条件", "需外协或合作", "不做湿实验"]},
    {"key": "ethics", "label": "伦理与合规", "group": "规范与合规",
     "options": ["已获伦理批件", "在办", "需生物安全备案", "不适用"]},
    {"key": "reporting", "label": "报告规范", "group": "规范与合规",
     "options": ["ARRIVE 2.0（动物实验）", "CONSORT（随机试验）", "PRISMA（系统综述）",
                 "STROBE（观察性研究）", "TRIPOD（预测模型）", "不适用"]},
    {"key": "data_policy", "label": "数据管理", "group": "规范与合规",
     "options": ["FAIR + 数据管理计划", "仅内部归档", "待定"]},
    {"key": "assessment", "label": "成果评价口径", "group": "成果评价",
     "options": ["DORA 原则（代表作/质量/贡献）", "单位职称评审口径",
                 "项目验收口径", "未指定"]},
)

DIMENSIONS: tuple[dict, ...] = (
    {"key": "pi", "label": "负责人学术水平", "label_en": "PI academic standing", "weight": 0.30,
     "hint": "看代表作与具体贡献，不以期刊影响因子、h-index 或数量代替质量",
     "options": [
         {"level": 1, "label": "无独立通讯作者成果", "criteria": "仅有参与作者论文，代表作尚不能说明独立贡献"},
         {"level": 2, "label": "有通讯作者成果", "criteria": "有通讯作者论文，代表作可逐篇说明作者位次与贡献"},
         {"level": 3, "label": "代表作质量稳定", "criteria": "代表作经同行认可，方法、数据或理论贡献可核验"},
         {"level": 4, "label": "代表作被同行采用", "criteria": "代表作被复现、采纳、写入指南/教材，或获领域奖励"},
         {"level": 5, "label": "持续高质量产出与引领", "criteria": "多篇代表作形成连续贡献，参与领域标准/共同体建设"},
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

DEFAULTS_IDENTITY = {"unit": "", "department": "", "unit_ror": "", "unit_official": "",
                     "role": "博士生", "org": "省部级重点实验室/平台",
                     "author": "", "author_title": "教授/正高",
                     "author_openalex": "", "author_orcid": "", "author_doi": "",
                     "lookup_confidence": "", "lookup_note": "",
                     "representative": "", "open_science": "部分开放",
                     "group_size": "4–8 人", "project": "省部级项目"}
DEFAULTS_CONDITIONS = {"experiment": "干湿结合", "data_source": "共享数据库",
                       "platform_access": "校内共享平台", "budget": "5–20 万",
                       "period": "1 年", "wet": "具备湿实验条件",
                       "ethics": "不适用", "reporting": "不适用",
                       "data_policy": "FAIR + 数据管理计划",
                       "assessment": "DORA 原则（代表作/质量/贡献）"}


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
            limit = 220 if key in ("unit_ror", "author_openalex", "author_orcid",
                                   "author_doi", "lookup_note") else 80
            data["identity"][key] = value[:limit]
    if not data["identity"].get("department") and data["identity"].get("unit"):
        match = re.match(r"^(.{2,}?(?:大学|学院|研究院|研究所|中心|医院|学校))(.{2,})$",
                         data["identity"]["unit"])
        if match:
            data["identity"]["unit"] = match.group(1)
            data["identity"]["department"] = match.group(2)
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
            {"key": "unit", "label": "单位（机构）", "type": "text",
             "placeholder": "例：兰州大学"},
            {"key": "department", "label": "院系/部门", "type": "text",
             "placeholder": "例：草地农业科技学院"},
            {"key": "role", "label": "申请人身份", "type": "select", "options": ROLES},
            {"key": "org", "label": "单位平台层级", "type": "select", "options": ORGS},
            {"key": "author", "label": "通讯作者", "type": "text", "placeholder": "姓名"},
            {"key": "author_title", "label": "通讯作者职称/层级", "type": "select",
             "options": AUTHOR_TITLES},
            {"key": "representative", "label": "代表作与贡献", "type": "text",
             "placeholder": "例：3 篇代表作，注明作者位次与个人贡献"},
            {"key": "open_science", "label": "开放科学实践", "type": "select",
             "options": ["数据与代码开放", "部分开放", "仅论文", "待定"]},
            {"key": "group_size", "label": "课题组人数", "type": "select", "options": GROUP_SIZES},
            {"key": "project", "label": "在研项目层级", "type": "select", "options": PROJECTS},
        ],
        "conditions": [{"key": c["key"], "label": c["label"], "group": c.get("group", ""),
                        "options": c["options"]}
                       for c in CONDITIONS],
        "dimensions": [{"key": d["key"], "label": d["label"], "label_en": d["label_en"],
                        "weight": d["weight"], "hint": d["hint"],
                        "options": [{"level": o["level"], "label": o["label"],
                                     "criteria": o["criteria"]} for o in d["options"]]}
                       for d in DIMENSIONS],
    }


def _full_unit(identity: dict) -> str:
    unit = str(identity.get("unit") or "").strip()
    department = str(identity.get("department") or "").strip()
    if not unit:
        return department
    if not department or department in unit:
        return unit
    cjk = lambda s: bool(s) and "\u4e00" <= s[0] <= "\u9fff"  # noqa: E731
    sep = "" if (cjk(unit) and cjk(department)) else " "
    return f"{unit}{sep}{department}"


def markdown_block(profile: dict | None = None) -> list[str]:
    result = evaluate(profile)
    identity = result["identity"]
    full_unit = _full_unit(identity)
    lines = ["### 课题组条件与可行性", "",
             f"- 综合得分：**{result['score']} / 5**（{result['band']}）——{result['advice']}",
             f"- 单位：{full_unit or '待申请人补充'}；"
             f"申请人身份：{identity.get('role')}；"
             f"通讯作者：{(identity.get('author') or '待补')}（{identity.get('author_title')}）；"
             f"课题组规模：{identity.get('group_size')}；在研项目：{identity.get('project')}",
             f"- 代表作与贡献：{identity.get('representative') or '待申请人按代表作逐篇说明'}；"
             f"开放科学实践：{identity.get('open_science')}"]
    verify = []
    if identity.get("unit_ror"):
        verify.append(f"单位 ROR：{identity['unit_ror']}")
    if identity.get("author_orcid"):
        verify.append(f"通讯作者 ORCID：{identity['author_orcid']}")
    if identity.get("author_doi"):
        verify.append(f"核验 DOI：{identity['author_doi']}")
    if identity.get("lookup_confidence"):
        verify.append(f"身份核验置信度：{identity['lookup_confidence']}")
    if verify:
        lines.append("- 身份核验：" + "；".join(verify) +
                     (f"；{identity['lookup_note']}" if identity.get("lookup_note") else ""))
    lines += ["- 五维评级（1–5 级；权重按通讯评议常用结构，可按本单位口径调整）：", "",
              "| 维度 | 权重 | 评级 | 档位判据 | 来源 |", "| --- | --- | --- | --- | --- |"]
    for row in result["rows"]:
        origin = "自动推算" if row["source"] == "auto" else "手工填写"
        lines.append(f"| {row['label']} | {row['weight']:.2f} | {row['level']} | "
                     f"{row['option']}（{row['criteria']}） | {origin} |")
    cond = result["conditions"]
    lines += ["", "### 研究条件与规范", "",
              "| 类别 | 条件 | 取值 |", "| --- | --- | --- |"]
    for spec in CONDITIONS:
        lines.append(f"| {spec.get('group', '')} | {spec['label']} | {cond.get(spec['key'], '')} |")
    lines += ["",
              "- 成果评价口径：DORA 原则——以代表作、具体贡献与研究质量为主，"
              "不把期刊影响因子、h-index、引用数当作单个替代指标。",
              "- 报告规范：动物实验 ARRIVE 2.0；随机试验 CONSORT；系统综述 PRISMA；"
              "观察性研究 STROBE；预测模型 TRIPOD；不适用的写“不适用”。",
              "- 数据管理：按 FAIR 原则归档，并在方案中给出数据管理计划（DMP）；"
              "受试者数据、动物伦理与生物安全按本单位规定审批。"]
    if result["gaps"]:
        lines += ["", f"- 短板：{'、'.join(result['gaps'])}。"
                      "方案里要写明补法（合作、共享平台、缩小目标或分期实施）。"]
    lines += ["", "> 以上只用于判断选题与现有条件是否匹配，不替代同行评议结论。"]
    return lines

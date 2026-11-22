"""研究群目录：机构用 ROR，组织单元用本地权威档，研究组只挂正式单元。

设计口径：
- 机构层固定为 ROR；院系没有全球库，按学院官网机构设置页维护；
- 组织单元按 CERIF OrgUnit 的父子层级、负责人、成员、来源与有效期建模；
- 研究所/中心是正式组织单元，进目录；课题组/研究组作为可选下钻，不单独冒充正式机构；
- 目录只收官网可核对的信息，字段带 source 与 verified；不按姓名、论文数猜职称或人头；
- 搜索只负责“找到哪个研究群”，不替用户判断某个人是谁。
"""
from __future__ import annotations

import re
from typing import Any

INSTITUTION = {
    "id": "lzu",
    "name": "兰州大学",
    "name_en": "Lanzhou University",
    "type": "university",
    "ror": "https://ror.org/01mkqqe32",
    "country": "中国",
}

COLLEGE = {
    "id": "lzu-caoye",
    "name": "草地农业科技学院",
    "name_en": "College of Pastoral Agriculture Science and Technology",
    "type": "college",
    "parent_id": "lzu",
    "source": "https://caoye.lzu.edu.cn/xueyuangaikuang/jigoushezhi/index.html",
}

COLLEGE_SOURCE = "https://caoye.lzu.edu.cn/xueyuangaikuang/jigoushezhi/index.html"
CENTER_SOURCE = "http://cgm.lzu.edu.cn/index.htm"
VERIFIED = "2026-11-22"
PLATFORM = "草种创新与草地农业生态系统全国重点实验室"

_COMMON = {
    "institution": "兰州大学",
    "department": "草地农业科技学院",
    "unit_ror": INSTITUTION["ror"],
    "parent_id": COLLEGE["id"],
    "platform": f"{PLATFORM}（学院共享，按课题组实际使用核对）",
    "source": COLLEGE_SOURCE,
    "verified": VERIFIED,
}

_GROUPS: tuple[dict[str, Any], ...] = (
    {
        **_COMMON, "id": "lzu-caoye-grassland-protection",
        "name": "草地保护研究所", "short": "草保所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["草地保护所", "草地保护", "草保"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-breeding-seed",
        "name": "草类植物育种与种子研究所", "short": "育种与种子所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["草类植物育种与种子所", "育种与种子所", "育种所", "草种所", "种子所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-grassland-ecology",
        "name": "草地生态研究所", "short": "生态所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["草地生态所", "生态所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-rural-grassland",
        "name": "农区草业研究所", "short": "农区草业所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["农区草业所", "农区所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-element-management",
        "name": "草业系统元素利用与管理研究所", "short": "元素利用所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["草业系统元素利用与管理所", "元素利用所", "元素所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-livestock-system",
        "name": "草畜生产系统调控研究所", "short": "草畜调控所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["草畜生产系统调控所", "草畜调控所", "草畜所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-ruminant",
        "name": "反刍动物研究所", "short": "反刍所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["反刍动物所", "反刍所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-stress-physiology",
        "name": "草类植物逆境生理与遗传改良研究所", "short": "逆境生理所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["草类植物逆境生理与遗传改良所", "逆境生理所", "逆境所", "遗传改良所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-remote-sensing-gis",
        "name": "草地遥感与地理信息系统研究所", "short": "遥感与GIS所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["草地遥感与地理信息系统所", "遥感与GIS所", "遥感所", "GIS所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-system-analysis",
        "name": "草业系统分析和社会发展研究所", "short": "系统分析所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["草业系统分析和社会发展所", "草业系统分析所", "系统分析所", "社会发展所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON,
        "id": "lzu-caoye-microbial-center",
        "name": "草地微生物研究中心", "short": "草微中心", "type": "center",
        "type_label": "研究中心",
        "aliases": ["草微中心", "草地微生物中心", "微生物中心", "草微"],
        "leader": "南志标",
        "deputy_leaders": ["苟小军", "杨云锋"],
        "chief_scientist": "周集中",
        "members": ["邓建明", "李祥锴", "张金林"],
        "directions": ["草地土壤微生物", "植物微生物", "动物微生物", "系统微生物学理论与技术"],
        "platform": f"{PLATFORM}（中心依托）",
        "platform_level": "全国重点实验室",
        "source": CENTER_SOURCE,
        "verified": VERIFIED,
        "note": "中心 2019 年成立；官网教师风采只列部分成员，完整名单需向中心确认。",
    },
)


def _norm(text: str) -> str:
    return re.sub(r"[\s\-_,，。；;：:、/\\|（）()\[\]【】.·'\"“”]+", "", str(text or "").lower())


def _terms(group: dict[str, Any]) -> list[str]:
    terms = [group.get("name", ""), group.get("short", "")]
    terms += list(group.get("aliases") or [])
    return [term for term in terms if term]


def _haystack(group: dict[str, Any]) -> str:
    return "|".join(_norm(term) for term in _terms(group))


def search(query: str = "", limit: int = 11) -> list[dict[str, Any]]:
    """按名称/简称/别名检索；空查询返回全部，供下拉直接浏览。"""
    q = _norm(query)
    if not q:
        return [dict(group) for group in _GROUPS[:limit]]
    rows: list[tuple[int, dict[str, Any]]] = []
    for group in _GROUPS:
        score = 0
        for term in _terms(group):
            t = _norm(term)
            if not t:
                continue
            if t == q:
                score = max(score, 100)
            elif t.startswith(q):
                score = max(score, 80)
            elif q in t:
                score = max(score, 60)
        if score:
            rows.append((score, group))
    rows.sort(key=lambda item: (-item[0], item[1].get("name", "")))
    return [dict(group) for _, group in rows[:limit]]


def get(group_id: str) -> dict[str, Any] | None:
    gid = str(group_id or "").strip()
    if not gid:
        return None
    for group in _GROUPS:
        if group["id"] == gid:
            return dict(group)
    return None


def resolve(identity: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """从 group_id 或 research_group 名称找到唯一研究群；找不到/不唯一都返回 None。"""
    row = identity or {}
    group = get(row.get("group_id") or "")
    if group:
        return group
    name = str(row.get("research_group") or "").strip()
    if not name:
        return None
    rows = search(name)
    exact = [g for g in rows if g.get("name") == name or g.get("short") == name]
    return exact[0] if len(exact) == 1 else None


def _leader_text(group: dict[str, Any]) -> str:
    parts: list[str] = []
    if group.get("leader"):
        parts.append(f"{group['leader']}（主任）" if group.get("type") == "center" else group["leader"])
    if group.get("deputy_leaders"):
        parts.append("、".join(group["deputy_leaders"]) + "（副主任）")
    if group.get("chief_scientist"):
        parts.append(f"{group['chief_scientist']}（首席科学家）")
    return "；".join(parts)


def identity_patch(group: dict[str, Any]) -> dict[str, str]:
    """把研究群档案映射到课题组表单；只放官网可核对字段。"""
    patch = {
        "unit": INSTITUTION["name"],
        "department": COLLEGE["name"],
        "unit_ror": INSTITUTION["ror"],
        "unit_official": INSTITUTION["name"],
        "research_group": group["name"],
        "group_id": group["id"],
        "group_short": group.get("short", ""),
        "group_type": group.get("type_label", ""),
        "group_leader": _leader_text(group),
        "group_directions": "；".join(group.get("directions") or []),
        "group_platform": group.get("platform", ""),
        "group_source": group.get("source", ""),
        "group_verified": group.get("verified", ""),
    }
    if group.get("platform_level"):
        patch["org"] = group["platform_level"]
    return patch


def evidence(group: dict[str, Any]) -> dict[str, Any]:
    """只给“这个研究群有官网档案”的结构化证据，不用论文数反推职称。"""
    dirs = group.get("directions") or []
    members = group.get("members") or []
    return {
        "group_id": group["id"],
        "group_name": group["name"],
        "group_type": group.get("type_label", ""),
        "has_leader": bool(group.get("leader")),
        "direction_count": len(dirs),
        "known_member_count": len(members),
        "platform_level": group.get("platform_level", ""),
        "source": group.get("source", ""),
        "verified": group.get("verified", ""),
        "note": f"研究群档案已带入：{group['name']}；来源 {group.get('source', '')}；核验 {group.get('verified', '')}",
    }


def as_json(group: dict[str, Any]) -> dict[str, Any]:
    """给前端的紧凑记录，保留目录字段，不塞推断值。"""
    return {
        "id": group["id"],
        "name": group["name"],
        "short": group.get("short", ""),
        "type": group.get("type", ""),
        "type_label": group.get("type_label", ""),
        "unit": group.get("institution", ""),
        "department": group.get("department", ""),
        "unit_ror": group.get("unit_ror", ""),
        "leader": _leader_text(group),
        "members": group.get("members") or [],
        "directions": group.get("directions") or [],
        "platform": group.get("platform", ""),
        "platform_level": group.get("platform_level", ""),
        "source": group.get("source", ""),
        "verified": group.get("verified", ""),
        "note": group.get("note", ""),
        "parent_id": group.get("parent_id", ""),
    }


def all_groups() -> list[dict[str, Any]]:
    return [as_json(group) for group in _GROUPS]

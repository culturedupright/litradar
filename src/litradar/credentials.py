"""检索源目录与本地凭据。

凭据只落在用户目录（LITRADAR_HOME/credentials.json），不进仓库、不进日志、不回显明文。
WOS / Scopus 没有“账号密码登录”的公开接口，权威做法是 API Key（走机构订阅额度），
所以这里保存的是 Key；过期时间由使用者填，过期即视为未登录，运行前自动跳过。

CNKI / 万方 / 维普 / CSCD / CSSCI 走机构 IP 或校园 VPN，不保存账号密码；
界面只提供入口与题录核对，不在后台模拟登录或绕付费墙。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .config import HOME

PATH = Path(os.environ.get("LITRADAR_CREDENTIALS", HOME / "credentials.json"))

# 顺序即“权威程度”排序：一级索引 → 中文核心索引 → 专业文摘 → 开放元数据 → 预印本。
SPECS: dict[str, dict] = {
    "wos": {
        "label": "Web of Science", "rank": 1, "tier": "一级索引",
        "scope": "SCIE / SSCI / AHCI / CPCI", "access": "key", "direct": True,
        "fields": [("api_key", "API Key"), ("expires", "有效期至（YYYY-MM-DD，可空）")],
        "optional": ["expires"],
        "help": "Clarivate 开发者门户申请，走机构订阅额度",
        "note": "国际公认的引文索引；兰大已购 SCIE/SSCI/AHCI/JCR/CPCI，以图书馆当期开通为准",
        "url": "https://www.webofscience.com/",
    },
    "scopus": {
        "label": "Scopus", "rank": 2, "tier": "一级索引",
        "scope": "全球多学科摘要与引文", "access": "key", "direct": True,
        "fields": [("api_key", "Elsevier API Key"), ("inst_token", "机构 Token（可空）"),
                   ("expires", "有效期至（YYYY-MM-DD，可空）")],
        "optional": ["inst_token", "expires"],
        "help": "Elsevier 开发者门户申请，机构订阅下可用",
        "note": "覆盖范围略宽于 WOS，引用数据可用于交叉核对；是否开通以本校图书馆为准",
        "url": "https://www.scopus.com/",
    },
    "cnki": {
        "label": "中国知网 CNKI", "rank": 3, "tier": "中文核心索引",
        "scope": "中文期刊 / 学位论文 / 会议 / 年鉴", "access": "subscription", "direct": False,
        "fields": [("institution", "机构名称（可空）"), ("portal", "机构入口（可空）")],
        "optional": ["institution", "portal"],
        "help": "校园网或 VPN 访问；不保存账号密码",
        "note": "北大核心、CSSCI、CSCD 的主要收录平台；无公开检索 API，题录在浏览器核对后引用",
        "url": "https://www.cnki.net/",
    },
    "cscd": {
        "label": "CSCD 中国科学引文数据库", "rank": 4, "tier": "中文核心索引",
        "scope": "中文科技期刊引文", "access": "subscription", "direct": False,
        "fields": [("institution", "机构名称（可空）")],
        "optional": ["institution"],
        "help": "中科院文献情报中心；多数高校以机构 IP 开通",
        "note": "中文科技核心期刊与引文口径，适合核对国内同行工作",
        "url": "https://www.cscd.ac.cn/",
    },
    "cssci": {
        "label": "CSSCI 中文社会科学引文索引", "rank": 5, "tier": "中文核心索引",
        "scope": "中文人文社科期刊引文", "access": "subscription", "direct": False,
        "fields": [("institution", "机构名称（可空）")],
        "optional": ["institution"],
        "help": "南京大学中国社会科学研究评价中心；机构 IP 开通",
        "note": "人文社科方向的中文核心口径，和 SSCI 互补",
        "url": "https://cssrac.nju.edu.cn/",
    },
    "wanfang": {
        "label": "万方数据", "rank": 6, "tier": "中文全文库",
        "scope": "期刊 / 学位论文 / 会议 / 标准", "access": "subscription", "direct": False,
        "fields": [("institution", "机构名称（可空）")],
        "optional": ["institution"],
        "help": "校园网或 VPN 访问；不保存账号密码",
        "note": "中文全文与学位论文补充；兰大已购，适合找中文硕博论文的方法细节",
        "url": "https://www.wanfangdata.com.cn/",
    },
    "cqvip": {
        "label": "维普中文期刊", "rank": 7, "tier": "中文全文库",
        "scope": "中文期刊全文", "access": "subscription", "direct": False,
        "fields": [("institution", "机构名称（可空）")],
        "optional": ["institution"],
        "help": "校园网或 VPN 访问；不保存账号密码",
        "note": "中文期刊覆盖面较广；兰大已购，作为知网/万方的交叉核对",
        "url": "https://www.cqvip.com/",
    },
    "pubmed": {
        "label": "PubMed / MEDLINE", "rank": 8, "tier": "专业文摘",
        "scope": "生物医学与生命科学", "access": "open", "direct": True,
        "fields": [("email", "联系邮箱（可选，NCBI 建议填）")],
        "optional": ["email"],
        "help": "无需登录；填邮箱可提高限流额度",
        "note": "MEDLINE 是生医领域最权威的题录库；只给题录与摘要，全文看 PMC/OA",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
    },
    "europepmc": {
        "label": "Europe PMC", "rank": 9, "tier": "专业文摘",
        "scope": "生命科学 / 预印本 / 专利", "access": "open", "direct": True,
        "fields": [], "optional": [],
        "help": "无需登录，开放接口",
        "note": "PubMed 的欧洲镜像并扩展预印本；生医方向可作全文与图注来源",
        "url": "https://europepmc.org/",
    },
    "crossref": {
        "label": "Crossref", "rank": 10, "tier": "开放元数据",
        "scope": "全球 DOI 题录", "access": "open", "direct": True,
        "fields": [("email", "联系邮箱（可选，进入 polite pool）")],
        "optional": ["email"],
        "help": "无需登录；填邮箱提高请求配额",
        "note": "DOI 注册库，题录最全；摘要覆盖率一般，适合补全引文信息",
        "url": "https://www.crossref.org/",
    },
    "openalex": {
        "label": "OpenAlex", "rank": 11, "tier": "开放元数据",
        "scope": "全球多学科题录与引用", "access": "open", "direct": True,
        "fields": [("email", "联系邮箱（可选）")],
        "optional": ["email"],
        "help": "无需登录；填邮箱进入 polite pool",
        "note": "开放引用图谱，覆盖全学科；适合跨库去重与引用核对",
        "url": "https://openalex.org/",
    },
    "semanticscholar": {
        "label": "Semantic Scholar", "rank": 12, "tier": "开放元数据",
        "scope": "多学科题录 / 引用 / TLDR", "access": "open", "direct": True,
        "fields": [("api_key", "API Key（可选）")],
        "optional": ["api_key"],
        "help": "免登录可用；有 Key 时配额更高",
        "note": "AI 辅助的语义检索；作为 OpenAlex/Crossref 的补充召回",
        "url": "https://www.semanticscholar.org/",
    },
    "arxiv": {
        "label": "arXiv", "rank": 13, "tier": "预印本",
        "scope": "物理 / 数学 / 计算机 / 定量生物等", "access": "open", "direct": True,
        "fields": [], "optional": [],
        "help": "无需登录，开放接口",
        "note": "预印本未经同行评议，引用时须注明版本与“preprint”",
        "url": "https://arxiv.org/",
    },
}

MASKED = "••••••••"


def _load() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 文件不存在或损坏都当作空
        return {}


def _save(data: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(PATH, 0o600)
    except OSError:
        pass


def _expired(entry: dict) -> bool:
    expires = str(entry.get("expires") or "").strip()
    if not expires:
        return False
    try:
        return time.mktime(time.strptime(expires, "%Y-%m-%d")) < time.time()
    except ValueError:
        return False


def _required(spec: dict) -> list[str]:
    optional = set(spec.get("optional", []) + ["email", "expires", "inst_token", "institution", "portal"])
    return [key for key, _label in spec.get("fields", []) if key not in optional]


def active(source: str) -> dict | None:
    """返回可用凭据；过期或缺少必填项都返回 None。"""
    entry = _load().get(source) or {}
    if _expired(entry):
        return None
    spec = SPECS.get(source, {})
    if spec.get("access") == "subscription":
        return entry or None
    for key in _required(spec):
        if not str(entry.get(key) or "").strip():
            return None
    return entry or {}


def status(source: str) -> dict:
    entry = _load().get(source) or {}
    spec = SPECS.get(source, {})
    access = spec.get("access", "key")
    expired = bool(entry) and _expired(entry)
    if access == "open":
        configured = True
    elif access == "subscription":
        configured = True
    else:
        configured = bool(entry) and not expired
        for key in _required(spec):
            if not str(entry.get(key) or "").strip():
                configured = False
    return {
        "source": source,
        "label": spec.get("label", source),
        "rank": spec.get("rank", 99),
        "tier": spec.get("tier", ""),
        "scope": spec.get("scope", ""),
        "access": access,
        "direct": bool(spec.get("direct", True)),
        "url": spec.get("url", ""),
        "note": spec.get("note", ""),
        "free": access in ("open", "subscription"),
        "help": spec.get("help", ""),
        "fields": [{"key": k, "label": v} for k, v in spec.get("fields", [])],
        "configured": configured,
        "expired": expired,
        "expires": entry.get("expires", ""),
        "saved_at": entry.get("saved_at", ""),
        "masked": MASKED if entry.get("api_key") else "",
    }


def all_status() -> list[dict]:
    return [status(key) for key in sorted(SPECS, key=lambda k: SPECS[k].get("rank", 99))]


def save(source: str, values: dict) -> dict:
    if source not in SPECS:
        raise ValueError(f"未知检索源：{source}")
    data = _load()
    allowed = {"api_key", "email", "inst_token", "expires", "institution", "portal"}
    entry = {k: str(v).strip() for k, v in values.items() if k in allowed}
    entry["saved_at"] = time.strftime("%Y-%m-%d %H:%M")
    data[source] = entry
    _save(data)
    return status(source)


def clear(source: str) -> dict:
    data = _load()
    data.pop(source, None)
    _save(data)
    return status(source)


def mask(value: str) -> str:
    value = str(value or "")
    return value[:4] + MASKED if len(value) > 8 else MASKED

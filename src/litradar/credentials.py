"""检索源的本地凭据。

只落在用户目录（LITRADAR_HOME/credentials.json），不进仓库、不进日志、不回显明文。
WOS / Scopus 没有“账号密码登录”的公开接口，权威做法是 API Key（走机构订阅额度），
所以这里保存的是 Key；过期时间由使用者填，过期即视为未登录，运行前自动跳过。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .config import HOME

PATH = Path(os.environ.get("LITRADAR_CREDENTIALS", HOME / "credentials.json"))

# 每个源需要哪些字段、去哪儿拿
SPECS: dict[str, dict] = {
    "europepmc": {"label": "Europe PMC", "fields": [], "free": True,
                  "help": "无需登录，开放接口"},
    "pubmed": {"label": "PubMed", "fields": [("email", "联系邮箱（可选，NCBI 建议填）")],
               "free": True, "help": "无需登录；填邮箱可提高限流额度"},
    "openalex": {"label": "OpenAlex", "fields": [("email", "联系邮箱（可选）")],
                 "free": True, "help": "无需登录；填邮箱进入 polite pool"},
    "wos": {"label": "Web of Science", "fields": [("api_key", "API Key"), ("expires", "有效期至（YYYY-MM-DD，可空）")],
            "free": False, "help": "Clarivate 开发者门户申请，走机构订阅额度"},
    "scopus": {"label": "Scopus", "fields": [("api_key", "Elsevier API Key"), ("inst_token", "机构 Token（可空）"),
                                              ("expires", "有效期至（YYYY-MM-DD，可空）")],
               "free": False, "help": "Elsevier 开发者门户申请，机构订阅下可用"},
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


def active(source: str) -> dict | None:
    """返回可用凭据；过期或缺少必填项都返回 None。"""
    entry = _load().get(source) or {}
    if _expired(entry):
        return None
    spec = SPECS.get(source, {})
    for key, _label in spec.get("fields", []):
        if key in ("email", "expires", "inst_token"):
            continue
        if not str(entry.get(key) or "").strip():
            return None
    return entry or {}


def status(source: str) -> dict:
    entry = _load().get(source) or {}
    spec = SPECS.get(source, {})
    expired = bool(entry) and _expired(entry)
    configured = True if spec.get("free") else (bool(entry) and not expired)
    for key, _label in spec.get("fields", []):
        if key in ("email", "expires", "inst_token"):
            continue
        if not str(entry.get(key) or "").strip():
            configured = False
    return {
        "source": source,
        "label": spec.get("label", source),
        "free": bool(spec.get("free")),
        "help": spec.get("help", ""),
        "fields": [{"key": k, "label": v} for k, v in spec.get("fields", [])],
        "configured": configured,
        "expired": expired,
        "expires": entry.get("expires", ""),
        "saved_at": entry.get("saved_at", ""),
        "masked": MASKED if entry.get("api_key") else "",
    }


def all_status() -> list[dict]:
    return [status(key) for key in SPECS]


def save(source: str, values: dict) -> dict:
    if source not in SPECS:
        raise ValueError(f"未知检索源：{source}")
    data = _load()
    entry = {k: str(v).strip() for k, v in values.items() if k in {"api_key", "email", "inst_token", "expires"}}
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

"""从 DeepSeek Harness 自己的配置里发现可用模型。

DSH 把每个模型提供方写在 profile 的 `cordis.patch.yml` 里，形如：

    - id: llm-pi-ai
      name: "@deepseek-ai/dsh-llm-pi-ai"
      config:
        providers:
          ling:
            apiKeyEnv: LING_API_KEY
            baseURL: https://api.ant-ling.com/v1
            models:
              - id: Ling-3.0-flash

本模块只读这些配置，不复制、不猜测：面板里的模型列表因此和 DSH 自己看到的一致。
DeepSeek 官方那一支再向 `https://api.deepseek.com/v1/models` 实时探测一次，拿到
账号当前真正可用的模型。
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from .llm import dsh_keys

DSH_HOME = Path(os.environ.get("DSH_HOME", Path.home() / ".dsh"))
PROFILES = ("desktop", "web", "tauri", "safe")
OFFICIAL_PROVIDERS = {"deepseek", "deepseek-official", "deepseek-official"}
OFFICIAL_BASE = "https://api.deepseek.com/v1"
FALLBACK_OFFICIAL = ["deepseek-flash", "deepseek-v4-pro"]
NON_CHAT = ("asr", "tts", "audio", "image", "embed", "rerank")

_CACHE: tuple[float, dict[str, Any]] | None = None
_TTL = 600


def _profile_patch() -> Path | None:
    """取当前最可能在用的 profile 的 patch 层。"""
    for name in PROFILES:
        path = DSH_HOME / "profiles" / name / "cordis.patch.yml"
        if path.exists():
            return path
    return None


def _is_chat_model(model_id: str) -> bool:
    low = model_id.lower()
    return not any(word in low for word in NON_CHAT)


def _read_providers(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or []
    except yaml.YAMLError:
        return []
    providers: list[dict[str, Any]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        config = entry.get("config") or {}
        block = config.get("providers") if isinstance(config, dict) else None
        if not isinstance(block, dict):
            continue
        for provider_id, conf in block.items():
            if not isinstance(conf, dict):
                continue
            models = conf.get("models") or []
            entries = []
            for item in models:
                if isinstance(item, str):
                    model_id, label = item, item
                elif isinstance(item, dict):
                    model_id = str(item.get("id") or item.get("name") or "")
                    label = str(item.get("name") or model_id)
                else:
                    continue
                if model_id and _is_chat_model(model_id):
                    entries.append({"id": model_id, "label": label})
            if not entries:
                continue
            providers.append(
                {
                    "id": str(provider_id),
                    "label": str(conf.get("displayName") or provider_id),
                    "baseURL": str(conf.get("baseURL") or ""),
                    "apiKeyEnv": str(conf.get("apiKeyEnv") or ""),
                    "models": entries,
                }
            )
    return providers


def _probe_official(keys: dict[str, str]) -> list[str]:
    key = keys.get("DEEPSEEK_API_KEY", "")
    if not key:
        return []
    request = urllib.request.Request(
        f"{OFFICIAL_BASE}/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            body = json.loads(response.read())
        ids = [str(item.get("id") or "") for item in body.get("data", [])]
        return [model for model in ids if model and _is_chat_model(model)]
    except Exception:  # noqa: BLE001 - 探测失败就退回已知清单
        return []


def _decorate(providers: list[dict[str, Any]], keys: dict[str, str]) -> list[dict[str, Any]]:
    for provider in providers:
        env_name = provider.get("apiKeyEnv") or ""
        provider["key"] = bool(os.environ.get(env_name) or keys.get(env_name))
    return providers


def catalog(refresh: bool = False) -> dict[str, Any]:
    """返回 {providers, default, source}，带十分钟缓存。"""
    global _CACHE
    if _CACHE and not refresh and time.time() - _CACHE[0] < _TTL:
        return _CACHE[1]

    keys = dsh_keys()
    patch = _profile_patch()
    providers = _read_providers(patch)

    official_ids = _probe_official(keys)
    if not official_ids:
        official_ids = FALLBACK_OFFICIAL
    official = {
        "id": "deepseek-official",
        "label": "DeepSeek 官方",
        "baseURL": OFFICIAL_BASE,
        "apiKeyEnv": "DEEPSEEK_API_KEY",
        "models": [{"id": model, "label": model} for model in official_ids],
    }
    providers = [p for p in providers if p["id"] not in OFFICIAL_PROVIDERS] + [official]
    providers = _decorate(providers, keys)

    default = "deepseek-flash"
    if not any(m["id"] == default for p in providers for m in p["models"]):
        default = providers[-1]["models"][0]["id"]

    result = {
        "providers": providers,
        "default": default,
        "source": str(patch) if patch else "内置默认",
    }
    _CACHE = (time.time(), result)
    return result


def find(model_name: str) -> dict[str, Any] | None:
    """按模型 id 或 provider/model 找一条模型定义。"""
    wanted = (model_name or "").strip()
    if not wanted or wanted in ("deepseek", "ling"):
        return None
    data = catalog()
    for provider in data["providers"]:
        for model in provider["models"]:
            if model["id"] == wanted:
                return {**model, "provider": provider}
        if f"{provider['id']}/{wanted}" == wanted:
            return {"id": wanted, "provider": provider}
    return None


def list_models() -> dict[str, Any]:
    data = catalog()
    return {
        "default": data["default"],
        "source": data["source"],
        "providers": [
            {
                "id": provider["id"],
                "label": provider["label"],
                "key": provider.get("key", False),
                "models": provider["models"],
            }
            for provider in data["providers"]
        ],
    }

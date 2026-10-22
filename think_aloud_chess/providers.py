"""Provedores de API compatíveis com OpenAI (/chat/completions), configuráveis pela UI.

As chaves ficam SÓ em config.json (local). Nunca vão para as partidas, para exports nem para o navegador.
Modelo de um jogo: "opus" (CLI do Claude) ou "api:<provider_id>/<modelo>".
"""
import json
import threading
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from . import paths

CONFIG = paths.CONFIG
_lock = threading.Lock()


def _load():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {"providers": []}


def _save(cfg):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


def mask(key):
    return (key[:4] + "…" + key[-3:]) if key and len(key) > 8 else "•••"


def list_public():
    return [{"id": p["id"], "name": p["name"], "base_url": p["base_url"], "models": p["models"],
             "key": mask(p["api_key"]), "ready": bool(p["base_url"] and p["models"] and p["api_key"])}
            for p in _load()["providers"]]


def upsert(d):
    """Cria/atualiza. Campo vazio mantém o valor atual (a chave nunca volta do servidor)."""
    with _lock:
        cfg = _load()
        p = next((x for x in cfg["providers"] if x["id"] == d.get("id")), None)
        if p is None:
            p = {"id": uuid.uuid4().hex[:8], "name": "", "base_url": "", "api_key": "", "models": []}
            cfg["providers"].append(p)
        if d.get("name"):
            p["name"] = d["name"].strip()
        if d.get("base_url") is not None and d["base_url"].strip():
            p["base_url"] = d["base_url"].strip().rstrip("/")
        if d.get("api_key"):
            p["api_key"] = d["api_key"].strip()
        if d.get("models") is not None and (isinstance(d["models"], list) or str(d["models"]).strip()):
            ms = d["models"] if isinstance(d["models"], list) else str(d["models"]).split(",")
            p["models"] = [m.strip() for m in ms if m.strip()]
        _save(cfg)
        return p["id"]


def remove(pid):
    with _lock:
        cfg = _load()
        cfg["providers"] = [p for p in cfg["providers"] if p["id"] != pid]
        _save(cfg)


def get(pid):
    return next((p for p in _load()["providers"] if p["id"] == pid), None)


def parse_model(model):
    """'api:<pid>/<modelo>' -> (provider, modelo) ou None se for modelo do CLI."""
    if not model.startswith("api:"):
        return None
    pid, _, name = model[4:].partition("/")
    p = get(pid)
    if not p:
        raise ValueError("provedor não encontrado")
    return p, name


def fetch_models(provider, timeout=30):
    """GET {base_url}/models -> lista de ids (padrão OpenAI)."""
    req = urllib.request.Request(provider["base_url"] + "/models",
                                 headers={"Authorization": "Bearer " + provider["api_key"]})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}")
    except Exception as e:  # noqa
        raise RuntimeError(f"falha de rede: {type(e).__name__}")
    return sorted(m["id"] for m in data.get("data", []) if "id" in m)


def chat(provider, model, system, user, json_mode=False, timeout=600):
    """Chamada /chat/completions. Retorna (texto, {tokens, output_tokens, cached, cost, ms})."""
    import time
    if not (provider["base_url"] and provider["api_key"]):
        raise ValueError("provedor incompleto (falta URL base ou chave)")
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.7}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(provider["base_url"] + "/chat/completions", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + provider["api_key"]})
    t = time.time()
    try:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code != 400 or not json_mode:
                raise
            # alguns modelos/provedores não aceitam response_format: tenta de novo sem ele
            body.pop("response_format", None)
            req = urllib.request.Request(req.full_url, data=json.dumps(body).encode("utf-8"), headers=dict(req.header_items()))
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300].replace(provider["api_key"], "***")
        raise RuntimeError(f"HTTP {e.code}: {detail}")
    except Exception as e:  # noqa
        raise RuntimeError(f"falha de rede: {type(e).__name__}")
    text = data["choices"][0]["message"].get("content") or ""
    u = data.get("usage", {})
    return text, {"tokens": u.get("total_tokens", 0), "output_tokens": u.get("completion_tokens", 0),
                  "cached": u.get("prompt_cache_hit_tokens", 0), "cost": 0.0, "ms": int((time.time() - t) * 1000)}

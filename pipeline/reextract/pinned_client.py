"""pinned_client -- the pinned-options Ollama client shared by stage 1 (--read on) and stage 2.

Moved out of build_body_shadow.py (build_body_shadow re-exports every name). Every /api/chat payload is
sent with PINNED_OPTIONS and KEEP_ALIVE; every 200 reply's load_duration is recorded per call
(`calls`), the first must exceed RELOAD_S (the unload-verified load), no later one may. BR.RunFault is
THE exception type.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import body_read as BR  # noqa: E402
from body_read import RunFault  # noqa: E402,F401

PINNED_OPTIONS = {"seed": 0, "num_ctx": 16384, "num_batch": 512}
KEEP_ALIVE = "5m"
RELOAD_S = 1.0
HTTP_TIMEOUT_S = 30


def unload_model(client, base_url, model):
    """keep_alive:0 unload, then /api/ps must no longer list `model`. The only reset known to clear
    D's request-history state (2026-11-08). Returns the /api/ps listing after the unload."""
    root = base_url.rstrip("/")
    client.post(root + "/api/generate", json={"model": model, "keep_alive": 0}, timeout=120)
    ps = client.get(root + "/api/ps", timeout=HTTP_TIMEOUT_S).json()
    left = [m.get("name") for m in ps.get("models", [])]
    if model in left:
        raise RunFault(f"unload failed: {model} still listed by /api/ps ({left})")
    return ps


_dumps = json.dumps


def _sha8(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]


class PinnedClient:
    """Wraps the run's client. Every /api/chat payload is sent with PINNED_OPTIONS and KEEP_ALIVE (a
    caller value that differs is a RunFault, never overridden). Every 200 /api/chat reply's load_duration
    is recorded: the first must exceed RELOAD_S (the unload-verified load is triggered by the run's first
    call), no later one may (a mid-run reload). A violation is kept in .fault and raised as RunFault.
    `calls` holds one entry per 200 reply, appended BEFORE any fault check."""

    def __init__(self, inner):
        self.inner, self.base_url, self.model = inner, inner.base_url, inner.model
        self.load_durations_s = []
        self.options_sent = []
        self.calls = []
        self.fault = None

    def _fail(self, msg):
        if self.fault is None:
            self.fault = msg
        raise RunFault(msg)

    def get(self, url, timeout=None):
        return self.inner.get(url, timeout=timeout)

    def post(self, url, json=None, timeout=None):
        if not url.endswith("/api/chat"):
            return self.inner.post(url, json=json, timeout=timeout)
        opts = dict(json.get("options") or {})
        for k, v in PINNED_OPTIONS.items():
            if k in opts and opts[k] != v:
                self._fail(f"caller option {k}={opts[k]!r} conflicts with the pinned {v!r}")
            opts[k] = v
        if json.get("keep_alive", KEEP_ALIVE) != KEEP_ALIVE:
            self._fail(f"caller keep_alive {json.get('keep_alive')!r} conflicts with the pinned {KEEP_ALIVE!r}")
        sent = _dumps(opts, sort_keys=True)
        if sent not in self.options_sent:
            self.options_sent.append(sent)
        resp = self.inner.post(url, json=dict(json, options=opts, keep_alive=KEEP_ALIVE), timeout=timeout)
        if getattr(resp, "status_code", 200) == 200:
            n = len(self.load_durations_s)
            ld = resp.json().get("load_duration")
            msgs = json.get("messages") or [{}]
            imgs = msgs[0].get("images") or []
            entry = {"n": n,
                     "load_duration_s": round(ld / 1e9, 3)
                     if isinstance(ld, (int, float)) and not isinstance(ld, bool) else None,
                     "options_idx": self.options_sent.index(sent),
                     "prompt_sha8": _sha8(str(msgs[0].get("content", ""))),
                     "image_sha8": _sha8(imgs[0]) if imgs else None}
            self.calls.append(entry)
            if not isinstance(ld, (int, float)) or isinstance(ld, bool):
                self._fail(f"chat call {n}: reply carries no load_duration ({ld!r})")
            sec = ld / 1e9
            self.load_durations_s.append(round(sec, 3))
            if n == 0 and sec <= RELOAD_S:
                self._fail(f"chat call 0 did not trigger the load: load_duration {sec:.3f}s <= {RELOAD_S}s")
            if n > 0 and sec > RELOAD_S:
                self._fail(f"mid-run reload at chat call {n}: load_duration {sec:.3f}s > {RELOAD_S}s")
        return resp

    def load_trace(self):
        later = self.load_durations_s[1:]
        return {"chat_calls": len(self.load_durations_s),
                "first_load_s": self.load_durations_s[0] if self.load_durations_s else None,
                "max_later_load_s": max(later) if later else None, "fault": self.fault,
                "calls": self.calls}

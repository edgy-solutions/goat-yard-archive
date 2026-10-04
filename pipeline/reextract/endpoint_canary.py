# -*- coding: utf-8 -*-
"""A canary read, because an endpoint can go degenerate mid-run and keep answering.

    from endpoint_canary import Canary, CanaryFailed
    can = Canary(hostport, model, every=20)
    can.check("arm-start")                       # before the first real read
    ...
    can.tick(("p275:n1", "A2_spanbox"))          # after every read; checks every `every`
    can.check("arm-end")                         # before the arm is unloaded

WHY. Lane A2, 2026-10-04: endpoint **D** went degenerate after roughly 60 JSON-format image reads in a
single run -- it answered text prompts with `////` -- and recovered only on a model RELOAD. A later run
of 87 reads with canaries in it stayed healthy. Recorded in `gpu-servers.md`. Chris's instruction to
this lane: **use a canary read every batch on D, and abort on failure.**

WHAT A CANARY IS HERE, AND WHAT IT IS NOT. It is a liveness check on the SERVER, not a quality check on
a reading. It sends a text-only prompt whose answer is fixed and trivial and asks for it back. That is
the whole claim: at this moment, this model on this host can still produce a specified string. It says
nothing about whether an image read is correct -- and the lane's own rule applies to it, that a liveness
flag reading `full` is not a consistency check. A canary that passes is not evidence about the reads
around it; a canary that FAILS is evidence about them, which is the asymmetry that makes it worth the
call.

THE FAILURE IS RUN-LEVEL, NOT ITEM-LEVEL. The degeneracy is endpoint state, so the reads taken since
the last PASSING canary are suspect as a group -- not wrong, suspect, and nothing here can tell which.
So `tick`/`check` raise `CanaryFailed` carrying that list, the caller aborts the run rather than
skipping an item, and the list is written to the artifact. A later resume must refuse to inherit a
suspect read: `suspect_from_log()` is what a `done` set is filtered through, or the rerun splices
exactly the reads the canary was there to distrust.

TWO FAILURE MODES, BOTH CHECKED. The answer may be missing (the model replies with something else), or
the reply may be DEGENERATE in A2's sense -- a long run of one punctuation character, or a reply with no
letters or digits in it at all. The second is checked separately because `////` does not contain the
expected token either, and a report that only ever says "wrong answer" would not have told A2 what they
saw.
"""
import json
import re
import time

import httpx

# A fixed, meaningless token. It must not be a word the model could emit by accident in a refusal, and
# it must survive `think: false` on a model that likes to preface. Checked by `in`, not by equality.
NONCE = "WREN-7731"
PROMPT = ("Reply with exactly this text and nothing else: %s" % NONCE)
TIMEOUT = 120
RUN_OF_ONE = 8          # a run of >= 8 identical non-alphanumeric chars is A2's `////` signature


class CanaryFailed(RuntimeError):
    """Raised at the point of failure. `.record` is the row to write; `.suspect` is the read list."""

    def __init__(self, record, suspect):
        RuntimeError.__init__(self, "canary failed at %s: %s" % (record.get("where"),
                                                                 record.get("why")))
        self.record, self.suspect = record, suspect


def degenerate(text):
    """A2's symptom, not a quality judgement: a long single-character run, or no letters at all."""
    t = (text or "").strip()
    if not t:
        return "empty-reply"
    if not re.search(r"[0-9A-Za-z]", t):
        return "no-alphanumeric-characters:%r" % t[:40]
    m = re.search(r"([^0-9A-Za-z\s])\1{%d,}" % (RUN_OF_ONE - 1), t)
    if m:
        return "repeated-character-run:%r" % m.group(0)[:20]
    return None


def read_text(hostport, model, prompt=PROMPT, opts=None, timeout=TIMEOUT):
    """Text-only /api/chat with thinking off -- the same route the image reads use, minus the images."""
    r = httpx.post("http://%s/api/chat" % hostport,
                   json={"model": model, "think": False, "stream": False,
                         "options": dict(opts or {}, temperature=0),
                         "messages": [{"role": "user", "content": prompt}]},
                   timeout=timeout)
    r.raise_for_status()
    msg = r.json().get("message") or {}
    return (msg.get("content") or "").strip()


class Canary(object):
    def __init__(self, hostport, model, every=20, opts=None, reader=read_text):
        self.hostport, self.model, self.every = hostport, model, int(every)
        self.opts, self.reader = opts, reader
        assert self.every >= 1, "a canary every %r reads is not a cadence" % every
        self.log, self.since = [], []
        self.n_checks, self.n_reads = 0, 0

    # -- the two entry points ------------------------------------------------------------------
    def check(self, where):
        """Call the canary now. Raises CanaryFailed; on a pass, clears the suspect window."""
        t0 = time.time()
        try:
            txt, err = self.reader(self.hostport, self.model, opts=self.opts), None
        except Exception as e:                       # a transport failure is a failed canary, not a skip
            txt, err = "", "%s:%s" % (type(e).__name__, str(e)[:120])
        deg = degenerate(txt) if not err else None
        why = err or deg or (None if NONCE in txt else "expected-token-absent:%r" % txt[:60])
        rec = {"kind": "canary", "where": where, "model": self.model, "endpoint_host": self.hostport,
               "ok": why is None, "why": why, "degenerate": deg, "reply": txt[:200],
               "reads_since_last_pass": len(self.since), "secs": round(time.time() - t0, 1),
               "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        self.n_checks += 1
        if why is None:
            rec["suspect"] = []
            self.log.append(rec)
            self.since = []
            return rec
        rec["suspect"] = [list(x) for x in self.since]
        rec["note"] = ("endpoint degeneracy is server state, so every read since the last PASSING canary "
                       "is suspect as a group and none of them may be inherited by a resume. A2 saw this "
                       "recover only on a model reload.")
        self.log.append(rec)
        raise CanaryFailed(rec, list(self.since))

    def tick(self, key):
        """Record one real read; check on the cadence. `key` identifies the read for the suspect list."""
        self.since.append(key)
        self.n_reads += 1
        if self.n_reads % self.every == 0:
            return self.check("after-%d-reads" % self.n_reads)
        return None


def suspect_from_log(lines):
    """Every read a failed canary put in doubt, as keys -- filter a resume's `done` set through this."""
    out = set()
    for o in lines:
        if o.get("kind") == "canary" and not o.get("ok"):
            for k in o.get("suspect") or []:
                out.add(tuple(k))
    return out


if __name__ == "__main__":
    # Born test: the detector must fire on A2's actual symptom and must not fire on a good reply.
    assert degenerate("////////") and degenerate("") and degenerate("...............")
    assert degenerate(NONCE) is None and degenerate("The answer is %s." % NONCE) is None

    def _bad(hostport, model, opts=None):
        return "////////////"

    def _good(hostport, model, opts=None):
        return NONCE

    c = Canary("127.0.0.1:0", "m", every=2, reader=_good)
    c.check("start")
    assert c.tick(("a", "A2")) is None and c.tick(("b", "A2"))["ok"]
    c.reader = _bad
    try:
        c.tick(("c", "A2"))
        c.tick(("d", "A2"))
        raise SystemExit("FAIL: a degenerate reply did not raise")
    except CanaryFailed as e:
        assert [tuple(x) for x in e.suspect] == [("c", "A2"), ("d", "A2")], e.suspect
        assert suspect_from_log([e.record]) == {("c", "A2"), ("d", "A2")}
    print("endpoint_canary born test: detector fires on %r, passes on the nonce, suspect window "
          "spans exactly the reads since the last pass" % "////")

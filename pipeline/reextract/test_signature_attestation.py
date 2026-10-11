"""Hand-rolled test for signature_attestation (no pytest in the venv). ALL PAGE NUMBERS ARE FILE PAGES
(printed = file - 88). Rates and the p493:n3 result are asserted against the pinned signed exports."""
import io, json, sys
sys.stdout.reconfigure(encoding="utf-8")
import signature_attestation as SA
D = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits/"
P2 = D + "glyphsign_0401b636ffa7bf1a_pass2_26span_signed_3285d39a.jsonl"
P3 = D + "glyphsign_0401b636ffa7bf1a_pass3_3span_signed_51c0e7ba.jsonl"
load = lambda p: [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
fails = 0
def ok(n, c):
    global fails
    print(("  OK   " if c else "  FAIL ") + n); fails += 0 if c else 1
r2, r3 = load(P2), load(P3)
ok("pass-2 rate: 26 rows, 20 applicable, 15 unattested", SA.rate(r2) == (26, 20, 15))
ok("pass-3 rate: 3 rows, 3 applicable, 1 unattested", SA.rate(r3) == (3, 3, 1))
a2 = SA.attest(next(r for r in r2 if r["span_id"] == "p493:n3"))
a3 = SA.attest(next(r for r in r3 if r["span_id"] == "p493:n3"))
ok("p493:n3 pass-2 string is flagged", a2["signature_unattested"] is True)
ok("p493:n3 pass-3 string is flagged", a3["signature_unattested"] is True)
ok("p493:n3 flags BOTH readings, so it cannot discriminate the reversal", a2["derived_in_crop"] != a3["derived_in_crop"])
ok("the flag is None (n/a) when no in-crop signature", all(SA.attest(r)["signature_unattested"] is None
   for r in r2 if r["span_id"] in ("p275:n3", "p291:n0")))
print("RESULT", "FAIL" if fails else "PASS", fails)
sys.exit(1 if fails else 0)

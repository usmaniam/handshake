"""Two-stage delivery verifier. Deterministic checks are authoritative for failure;
the LLM can only turn PASS into FAIL/NEEDS_REVIEW, never the reverse."""
from __future__ import annotations

import base64
import hashlib
import struct
from datetime import date
from typing import Any

from defusedxml import ElementTree as SafeET

from ..flags import scan
from ..util import canon
from .llm import VERIFIER_SYSTEM, LLMError, LLMVerdict

PASS, FAIL, REVIEW = "PASS", "FAIL", "NEEDS_REVIEW"


def proof_key(proof: dict) -> str:
    if proof.get("proof_type") == "carrier_tracking":
        return "trk:" + str(proof.get("tracking_number", "")).strip().upper()
    files = sorted((f.get("name", ""), hashlib.sha256((f.get("content") or f.get("content_b64") or f.get("ref") or "").encode()).hexdigest())
                   for f in proof.get("files", []))
    return "files:" + hashlib.sha256(canon(files).encode()).hexdigest()[:40]


def _mk():
    checks: list[dict] = []

    def c(name: str, ok: bool, detail: str) -> bool:
        checks.append({"check": name, "passed": bool(ok), "detail": detail})
        return bool(ok)
    return checks, c


def check_physical(terms: Any, shipment: Any, consumed: bool) -> tuple[str, list[dict], bool]:
    checks, c = _mk()
    if shipment is None:
        c("tracking_found", False, "tracking number not found at carrier")
        return FAIL, checks, False
    c("tracking_found", True, f"{shipment.carrier} {shipment.tracking}")
    ok = c("carrier_delivered", shipment.status == "DELIVERED", f"carrier status is {shipment.status}")
    ok &= c("proof_unused", not consumed, "tracking number not used in another deal" if not consumed
            else "tracking number already used in another deal")
    spec = terms.spec or {}
    sku = spec.get("sku")
    items: dict[str, int] = {}
    for i in shipment.items or []:
        items[i.get("sku")] = items.get(i.get("sku"), 0) + int(i.get("qty", 0))
    got = items.get(sku, 0) if sku else sum(items.values())
    exp = terms.quantity
    if spec.get("destination"):
        ok &= c("destination", shipment.destination == spec["destination"],
                f"destination {shipment.destination!r} vs agreed {spec['destination']!r}")
    partial = False
    if got == exp:
        c("quantity_sku", True, f"{got} x {sku or 'items'} as agreed")
    elif got == 0:
        listed = ", ".join(f"{q} x {k}" for k, q in items.items()) or "nothing"
        ok &= c("quantity_sku", False, f"no {sku or 'items'} delivered (carrier lists {listed})")
    else:
        partial = True
        c("quantity_sku", False, f"{got} delivered vs {exp} agreed")
    late = bool(shipment.delivered_at and shipment.delivered_at.date() > terms.deadline)
    c("on_time", not late, "delivered after the deadline" if late else "within deadline")
    if not ok:
        return FAIL, checks, late
    return (REVIEW if partial else PASS), checks, late


def _png_dims(b64: str) -> tuple[int, int] | None:
    try:
        raw = base64.b64decode(b64, validate=True)
        if raw[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        return struct.unpack(">II", raw[16:24])
    except Exception:  # noqa: BLE001
        return None


def check_digital(terms: Any, proof: dict, delivered_on: date) -> tuple[str, list[dict], bool]:
    checks, c = _mk()
    spec, files = terms.spec or {}, proof.get("files", [])
    n, exp = len(files), spec.get("file_count")
    partial = False
    ok = True
    if exp is not None:
        if n == exp:
            c("file_count", True, f"{n} files")
        elif 0 < n < exp:
            partial = True
            c("file_count", False, f"{n} of {exp} files")
        else:
            ok &= c("file_count", False, f"{n} files vs {exp} agreed")
    exts = {e.lower().lstrip(".") for e in spec.get("extensions", [])}
    for f in files:
        name = f.get("name", "")
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if exts:
            ok &= c(f"type:{name}", ext in exts, f".{ext} {'allowed' if ext in exts else 'not in ' + str(sorted(exts))}")
        if spec.get("name_prefix"):
            ok &= c(f"name:{name}", name.startswith(spec["name_prefix"]), f"must start with {spec['name_prefix']!r}")
        if spec.get("max_bytes") and f.get("size"):
            ok &= c(f"size:{name}", f["size"] <= spec["max_bytes"], f"{f['size']} bytes (max {spec['max_bytes']})")
        if ext == "svg" and f.get("content"):
            try:
                SafeET.fromstring(f["content"])
                c(f"svg_parses:{name}", True, "valid SVG/XML")
            except Exception:  # noqa: BLE001
                ok &= c(f"svg_parses:{name}", False, "SVG does not parse")
        if ext == "png" and spec.get("min_width") and f.get("content_b64"):
            dims = _png_dims(f["content_b64"])
            ok &= c(f"dimensions:{name}", bool(dims and dims[0] >= spec["min_width"]),
                    f"{dims} vs min width {spec['min_width']}")
    for req in spec.get("required_extensions", []):
        ok &= c(f"has_{req}", any(f.get("name", "").lower().endswith("." + req.lower()) for f in files),
                f"a .{req} file is required")
    late = delivered_on > terms.deadline
    c("on_time", not late, "delivered after the deadline" if late else "within deadline")
    if not ok:
        return FAIL, checks, late
    return (REVIEW if partial else PASS), checks, late


def _deliverable_text(proof: dict) -> str:
    parts = [str(proof.get("notes", ""))]
    for f in proof.get("files", []):
        parts += [f.get("name", ""), f.get("content") or ""]
    return "\n".join(parts)


def verify_delivery(terms: Any, proof: dict, shipment: Any, consumed: bool, delivered_on: date, llm=None) -> dict:
    if terms.deliverable_type == "physical_goods":
        det, checks, late = check_physical(terms, shipment, consumed)
    else:
        det, checks, late = check_digital(terms, proof, delivered_on)
        if consumed:
            checks.append({"check": "proof_unused", "passed": False, "detail": "files already used in another deal"})
            det = FAIL
    text = _deliverable_text(proof)
    flags = scan(text)
    inj_local = "prompt_injection" in flags
    reasons = [f"{k['check']}: {k['detail']}" for k in checks if not k["passed"]]
    llm_out: dict = {"status": "skipped"}
    verdict = det
    if det == PASS and terms.deliverable_type == "digital_work" and llm is not None:
        payload = {"trusted_acceptance_criteria": terms.acceptance_criteria,
                   "untrusted_deliverable": {"notes": proof.get("notes", ""), "files": [
                       {"name": f.get("name"), "size": f.get("size"), "content": (f.get("content") or "")[:20000]}
                       for f in proof.get("files", [])]}}
        try:
            r: LLMVerdict = llm.json(VERIFIER_SYSTEM, canon(payload), LLMVerdict)
            llm_out = {"status": "ok", **r.model_dump()}
            verdict = r.verdict
            if r.injection_suspected or r.confidence < 0.7:
                verdict = REVIEW if verdict == PASS else verdict
                reasons.append("LLM flagged injection or low confidence")
            if r.verdict != PASS:
                reasons += [f"{x.criterion}: {x.evidence}" for x in r.criteria if not x.met]
            if r.injection_suspected:
                flags.append("llm_injection_suspected")
        except LLMError as e:
            llm_out = {"status": "error", "error": str(e)[:200]}
            verdict = REVIEW  # fail closed
            reasons.append("semantic check unavailable; owner review required")
    if inj_local and verdict == PASS:
        verdict = REVIEW
    if inj_local:
        reasons.append("deliverable contains instruction-like text (prompt injection suspected)")
    if verdict not in (PASS, FAIL, REVIEW) or (det != PASS and verdict == PASS):
        verdict = det if det != PASS else REVIEW  # never looser than deterministic
    return {"verdict": verdict, "deterministic": {"verdict": det, "checks": checks},
            "llm": llm_out, "reasons": reasons, "flags": flags, "late": late}

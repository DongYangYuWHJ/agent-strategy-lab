"""Read-only adapter using genuine serializers, signature checks and a virtual clock."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import hashlib
from itsdangerous import (Serializer, URLSafeSerializer, TimedSerializer,
                          URLSafeTimedSerializer, TimestampSigner, BadSignature, SignatureExpired)


def error_name(exc):
    # Contract names denote exception families; upstream timed errors are subclasses.
    if isinstance(exc, SignatureExpired):
        return "SignatureExpired"
    if isinstance(exc, BadSignature):
        return "BadSignature"
    return type(exc).__name__


def run(request):
    classes = {"plain": Serializer, "url": URLSafeSerializer,
               "timed": TimedSerializer, "url_timed": URLSafeTimedSerializer}
    now = [request.get("now", 1700000000)]
    class ClockSigner(TimestampSigner):
        def get_timestamp(self):
            return now[0]

    def make(spec):
        kind = spec.get("kind", request.get("kind", "url"))
        kw = {"salt": spec.get("salt", "lab"),
              "signer_kwargs": {"digest_method": getattr(hashlib, spec.get("digest", "sha256"))},
              "fallback_signers": []}
        if kind in ("timed", "url_timed"):
            kw["signer"] = ClockSigner
        return classes[kind](spec.get("keys", ["current"]), **kw)

    current = make(request.get("current", {}))
    if request["mode"] == "claims":
        if "raw" in request:
            token = current.dumps(request["raw"])
        else:
            token = current.dumps_claims(request.get("payload"), audience=request.get("audience", "api"),
                                         now=request.get("issued", 100), ttl=request.get("ttl", 20),
                                         not_before=request.get("not_before"))
        if request.get("tamper"):
            body, signature = token.rsplit(".", 1)
            token = body + "." + ("A" if signature[0] != "A" else "B") + signature[1:]
        verifier = make(request["verifier"]) if "verifier" in request else current
        try:
            result = verifier.loads_claims(token, audience=request.get("verify_audience", "api"),
                                           now=request.get("check_at", 110), leeway=request.get("leeway", 0))
            return {"value": result}
        except Exception as exc:
            return {"error": error_name(exc)}
    if request["mode"] == "invalid_issue":
        try:
            current.dumps_claims(request.get("payload"), **request["arguments"])
            return {"accepted": True}
        except Exception as exc:
            return {"error": error_name(exc)}
    if request["mode"] == "migration":
        origin = make(request.get("origin", {}))
        now[0] = request.get("signed_at", 1700000000)
        token = origin.dumps(request.get("payload"))
        if request.get("tamper"):
            body, signature = token.rsplit(".", 1)
            token = body + "." + ("A" if signature[0] != "A" else "B") + signature[1:]
        now[0] = request.get("checked_at", 1700000010)
        legacy = [make(spec) for spec in request.get("legacy", [])]
        try:
            result = current.migrate(token, legacy_serializers=iter(legacy), max_age=request.get("max_age"))
            output = {"value": result["value"], "source": result["source"],
                      "current_value": current.loads(result["token"])}
            if isinstance(current, TimedSerializer):
                _, timestamp = current.loads(result["token"], return_timestamp=True)
                output["signed_at"] = int(timestamp.timestamp())
                now[0] = request.get("later", 1700000030)
                try:
                    current.loads(result["token"], max_age=request.get("later_max_age", 20))
                    output["later"] = "valid"
                except Exception as exc:
                    output["later"] = error_name(exc)
            old = make(request.get("origin", {}))
            try:
                old.loads(result["token"])
                output["old_accepts"] = True
            except Exception:
                output["old_accepts"] = False
            return output
        except Exception as exc:
            return {"error": error_name(exc)}
    if request["mode"] == "claims_migration":
        origin = make(request.get("origin", {}))
        now[0] = request.get("signed_at", 1700000000)
        token = origin.dumps_claims(request.get("payload"), audience="api", now=100, ttl=20)
        now[0] = request.get("checked_at", 1700000010)
        migrated = current.migrate(token, legacy_serializers=[origin], max_age=request.get("max_age"))
        try:
            value = current.loads_claims(migrated["token"], audience=request.get("verify_audience", "api"),
                                        now=request.get("check_at", 110))
            result = {"value": value, "source": migrated["source"]}
        except Exception as exc:
            result = {"error": error_name(exc), "source": migrated["source"]}
        if isinstance(current, TimedSerializer):
            _, timestamp = current.loads(migrated["token"], return_timestamp=True)
            result["signed_at"] = int(timestamp.timestamp())
        return result
    if request["mode"] == "regression":
        token = current.dumps(request.get("payload"))
        return {"value": current.loads(token)}
    raise ValueError("Unknown mode")

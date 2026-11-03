"""Read-only adapter exercising the real signing and serialization modules."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import hashlib
from datetime import timezone
from itsdangerous import (Signer, TimestampSigner, Serializer, TimedSerializer,
                          URLSafeSerializer, URLSafeTimedSerializer, BadSignature)


CLASSES = {"plain": Serializer, "url": URLSafeSerializer,
           "timed": TimedSerializer, "url_timed": URLSafeTimedSerializer}


def rejects(serializer, token, **kwargs):
    try:
        serializer.loads(token, **kwargs)
        return False
    except BadSignature:
        return True


def run(request):
    mode = request["mode"]
    payload = request.get("payload", {"user": "alice"})
    if mode == "rotate":
        cls = CLASSES[request.get("serializer", "url")]
        salt = request.get("salt", "session")
        keys = request["keys"]
        settings = {"salt": salt}
        rotated = cls(keys, **settings)
        legacy = [cls(key, **settings).dumps(payload) for key in keys]
        current = rotated.dumps(payload)
        body, signature = current.rsplit(".", 1)
        tampered = body + "." + ("A" if signature[0] != "A" else "B") + signature[1:]
        return {"legacy_values": [rotated.loads(token) for token in legacy],
                "current": rotated.loads(current),
                "newest_accepts": not rejects(cls(keys[-1], **settings), current),
                "old_accepts": [not rejects(cls(k, **settings), current) for k in keys[:-1]],
                "wrong_salt_rejected": rejects(cls(keys, salt=salt + "-other"), current),
                "tamper_rejected": rejects(rotated, tampered)}
    if mode == "signer":
        keys = request["keys"]
        message = request["message"].encode("utf-8")
        salt = request.get("salt", "direct")
        signer = Signer(keys, salt=salt)
        current = signer.sign(message)
        return {"value": signer.unsign(current).decode("utf-8"),
                "legacy_valid": [signer.validate(Signer(k, salt=salt).sign(message)) for k in keys],
                "newest_valid": Signer(keys[-1], salt=salt).validate(current),
                "old_valid": [Signer(k, salt=salt).validate(current) for k in keys[:-1]],
                "other_valid": Signer("unrelated-key", salt=salt).validate(current)}
    if mode == "fallback":
        cls = CLASSES[request.get("serializer", "url")]
        keys = request["keys"]
        old = cls(keys[0], signer_kwargs={"digest_method": hashlib.sha1})
        token = old.dumps(payload)
        new = cls(keys, signer_kwargs={"digest_method": hashlib.sha256},
                  fallback_signers=[{"digest_method": hashlib.sha1}])
        new_token = new.dumps(payload)
        strict = cls(keys, signer_kwargs={"digest_method": hashlib.sha256}, fallback_signers=[])
        return {"legacy_value": new.loads(token), "current_value": strict.loads(new_token),
                "old_digest_rejected_without_fallback": rejects(strict, token),
                "current_accepted_by_newest": not rejects(cls(keys[-1], signer_kwargs={"digest_method": hashlib.sha256}), new_token)}
    if mode == "timed":
        clock = [request.get("signed_at", 1700000000)]

        class ClockSigner(TimestampSigner):
            def get_timestamp(self):
                return clock[0]

        cls = CLASSES[request.get("serializer", "url_timed")]
        settings = {"signer": ClockSigner}
        old = cls(request["keys"][0], **settings)
        token = old.dumps(payload)
        rotated = cls(request["keys"], **settings)
        clock[0] = request.get("now", clock[0])
        try:
            value, timestamp = rotated.loads(token, max_age=request.get("max_age"), return_timestamp=True)
            return {"value": value, "timestamp_utc": timestamp.tzinfo == timezone.utc,
                    "timestamp_seconds": int(timestamp.timestamp())}
        except BadSignature as exc:
            date = getattr(exc, "date_signed", None)
            return {"error": type(exc).__name__, "timestamp_utc": date is not None and date.tzinfo == timezone.utc}
    raise ValueError("Unknown scenario")

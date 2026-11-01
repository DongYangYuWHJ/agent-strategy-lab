import base64
import json
def encode(marker):
    payload = {"v": 1, "ts": marker[0], "id": marker[1]}
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
def decode(token):
    try:
        if type(token) is not str or not token:
            raise ValueError("invalid cursor")
        payload = json.loads(base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True))
        if (type(payload) is not dict or set(payload) != {"v", "ts", "id"}
                or type(payload["v"]) is not int or payload["v"] != 1
                or type(payload["ts"]) is not int or type(payload["id"]) is not int or payload["id"] < 1):
            raise ValueError("invalid cursor")
        return payload["ts"], payload["id"]
    except Exception as exc:
        raise ValueError("invalid cursor") from exc

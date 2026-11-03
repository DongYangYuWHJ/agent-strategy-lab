def dumps_claims(self, payload, *, audience, now, ttl, not_before=None):
    if (not isinstance(audience, str) or not audience or type(now) is not int
            or type(ttl) is not int or ttl <= 0):
        raise ValueError("Invalid claim arguments")
    not_before = now if not_before is None else not_before
    if type(not_before) is not int or not now <= not_before < now + ttl:
        raise ValueError("Invalid activation time")
    return self.dumps({"v": 1, "aud": audience, "iat": now, "nbf": not_before,
                       "exp": now + ttl, "payload": payload})


def loads_claims(self, token, *, audience, now, leeway=0):
    from .exc import BadSignature, SignatureExpired
    if (not isinstance(audience, str) or not audience or type(now) is not int
            or type(leeway) is not int or leeway < 0):
        raise ValueError("Invalid claim arguments")
    data = self.loads(token)
    if (not isinstance(data, dict) or set(data) != {"v", "aud", "iat", "nbf", "exp", "payload"}
            or type(data["v"]) is not int or data["v"] != 1
            or data["aud"] != audience
            or any(type(data[key]) is not int for key in ("iat", "nbf", "exp"))
            or not data["iat"] <= data["nbf"] < data["exp"]):
        raise BadSignature("Invalid claims")
    if now + leeway < data["nbf"] or now + leeway < data["iat"] or now >= data["exp"] + leeway:
        raise SignatureExpired("Claims not active")
    return data["payload"]

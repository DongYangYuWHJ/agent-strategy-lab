def migrate(self, token, *, legacy_serializers=(), max_age=None):
    from .exc import BadSignature, BadPayload, SignatureExpired
    from .timed import TimedSerializer
    timed = isinstance(self, TimedSerializer)
    if max_age is not None and (not timed or type(max_age) is not int or max_age < 0):
        raise ValueError("Invalid migration age")
    candidates = [self, *legacy_serializers]
    if any(not isinstance(item, Serializer) or isinstance(item, TimedSerializer) != timed
           for item in candidates):
        raise ValueError("Incompatible legacy serializer")
    last = None
    for index, serializer in enumerate(candidates):
        try:
            if timed:
                value, timestamp = serializer.loads(token, max_age=max_age, return_timestamp=True)
            else:
                value = serializer.loads(token)
        except SignatureExpired:
            raise
        except (BadSignature, BadPayload) as exc:
            last = exc if isinstance(exc, BadSignature) else BadSignature(str(exc))
            continue
        signer = self.make_signer()
        if timed:
            # This signer belongs only to this invocation; do not mutate a shared clock.
            epoch = int(timestamp.timestamp())
            signer.get_timestamp = lambda: epoch
        output = signer.sign(self.dump_payload(value))
        if self.is_text_serializer:
            output = output.decode("utf-8")
        return {"value": value, "token": output, "source": index}
    raise last

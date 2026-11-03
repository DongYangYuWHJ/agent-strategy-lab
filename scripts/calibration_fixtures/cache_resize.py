def resize(self, maxsize):
    if type(maxsize) is not int or maxsize <= 0:
        raise ValueError("maxsize must be a positive integer")
    if isinstance(self, _TimedCache):
        self.expire()
    evicted = []
    while self.currsize > maxsize:
        evicted.append(self.popitem())
    self._Cache__maxsize = maxsize
    return evicted

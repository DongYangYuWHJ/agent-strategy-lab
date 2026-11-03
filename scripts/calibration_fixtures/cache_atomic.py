def update_atomic(self, pairs):
    from copy import deepcopy
    staged = deepcopy(self)
    count = 0
    for key, value in pairs:
        staged[key] = value
        count += 1
    self.__dict__.clear()
    self.__dict__.update(staged.__dict__)
    return count

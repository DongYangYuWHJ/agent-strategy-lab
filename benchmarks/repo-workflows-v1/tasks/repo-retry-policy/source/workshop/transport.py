from copy import deepcopy
class Transport:
    def __init__(self, responses):
        self.responses = deepcopy(responses)
        self.attempts = 0
    def send(self):
        index = min(self.attempts, len(self.responses) - 1)
        self.attempts += 1
        return self.responses[index]

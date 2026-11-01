class Clock:
    def __init__(self):
        self.delays = []
    def sleep(self, seconds):
        self.delays.append(seconds)

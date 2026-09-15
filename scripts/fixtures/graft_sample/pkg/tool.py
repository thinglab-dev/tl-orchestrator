def add(a, b):
    """Add two integers."""
    return a + b


class Calculator:
    def __init__(self):
        self.total = 0

    def accumulate(self, value):
        self.total = add(self.total, value)
        return self.total

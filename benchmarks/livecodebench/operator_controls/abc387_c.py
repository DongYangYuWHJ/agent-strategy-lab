# Operator-written digit-counting positive control.
def count(limit):
    digits = [int(c) for c in str(limit)]
    length = len(digits)
    if length < 2:
        return 0
    total = sum(first ** (size - 1) for size in range(2, length) for first in range(1, 10))
    total += sum(first ** (length - 1) for first in range(1, digits[0]))
    first = digits[0]
    for index in range(1, length):
        total += min(digits[index], first) * first ** (length - index - 1)
        if digits[index] >= first:
            return total
    return total + 1


left, right = map(int, input().split())
print(count(right) - count(left - 1))

# Operator-written positive control: Boolean transition powers over a window of B cells.
import sys

data = iter(map(int, sys.stdin.read().split()))
n, m, a, b = next(data), next(data), next(data), next(data)
intervals = [(next(data), next(data)) for _ in range(m)]
mask = (1 << b) - 1


def apply(columns, state):
    value = 0
    while state:
        bit = state & -state
        value |= columns[bit.bit_length() - 1]
        state -= bit
    return value


columns = [((1 << (j + 1)) if j + 1 < b else 0) | (1 if j >= a - 1 else 0) for j in range(b)]
powers = [columns]
for _ in range(n.bit_length()):
    columns = [apply(columns, column) for column in columns]
    powers.append(columns)


def advance(state, length):
    index = 0
    while length and state:
        if length & 1:
            state = apply(powers[index], state)
        index += 1
        length >>= 1
    return state


state, position = 1, 1
for left, right in intervals:
    state = advance(state, left - position - 1)
    length = right - left + 1
    state = 0 if length >= b else (state << length) & mask
    position = right
state = advance(state, n - position)
print("Yes" if state & 1 else "No")

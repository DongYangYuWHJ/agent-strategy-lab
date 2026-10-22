# Operator-written positive control using integer geometry.
from math import isqrt

radius = int(input())
total = 0
for x in range(radius):
    y = (isqrt(4 * radius * radius - (2 * x + 1) ** 2) - 1) // 2
    if y >= 0:
        total += (1 if x == 0 else 2) * (2 * y + 1)
print(total)

# Operator-written positive control, not an upstream gold solution.
import sys

values = list(map(int, sys.stdin.read().split()))[1:]
print("Yes" if all(values[i] * values[0] == values[i - 1] * values[1]
                   for i in range(2, len(values))) else "No")

# Operator-written positive control: expand equal labels at both ends in a product graph.
from collections import deque

n = int(input())
grid = [input().strip() for _ in range(n)]
incoming, outgoing = [{} for _ in range(n)], [{} for _ in range(n)]
distance = [[-1] * n for _ in range(n)]
unseen = [(1 << n) - 1 for _ in range(n)]
queue = deque()
for i in range(n):
    distance[i][i] = 0
    unseen[i] &= ~(1 << i)
    queue.append((i, i))
for i in range(n):
    for j, label in enumerate(grid[i]):
        if label != "-":
            incoming[j].setdefault(label, []).append(i)
            outgoing[i][label] = outgoing[i].get(label, 0) | (1 << j)
            if i != j:
                distance[i][j] = 1
                unseen[i] &= ~(1 << j)
                queue.append((i, j))
while queue:
    left, right = queue.popleft()
    length = distance[left][right] + 2
    for label, predecessors in incoming[left].items():
        next_mask = outgoing[right].get(label, 0)
        for previous in predecessors:
            remaining = next_mask & unseen[previous]
            unseen[previous] &= ~remaining
            while remaining:
                bit = remaining & -remaining
                following = bit.bit_length() - 1
                distance[previous][following] = length
                queue.append((previous, following))
                remaining -= bit
for row in distance:
    print(*row)

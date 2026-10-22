# Operator-written positive control: Dijkstra over vertex and reversal parity.
import heapq
import sys

data = iter(map(int, sys.stdin.read().split()))
n, m, switch_cost = next(data), next(data), next(data)
forward, reverse = [[] for _ in range(n)], [[] for _ in range(n)]
for _ in range(m):
    a, b = next(data) - 1, next(data) - 1
    forward[a].append(b)
    reverse[b].append(a)
distance = [[10 ** 30] * n for _ in range(2)]
distance[0][0] = 0
queue = [(0, 0, 0)]
while queue:
    cost, parity, node = heapq.heappop(queue)
    if cost != distance[parity][node]:
        continue
    if node == n - 1:
        print(cost)
        break
    if cost + switch_cost < distance[1 - parity][node]:
        distance[1 - parity][node] = cost + switch_cost
        heapq.heappush(queue, (cost + switch_cost, 1 - parity, node))
    for following in (forward if parity == 0 else reverse)[node]:
        if cost + 1 < distance[parity][following]:
            distance[parity][following] = cost + 1
            heapq.heappush(queue, (cost + 1, parity, following))

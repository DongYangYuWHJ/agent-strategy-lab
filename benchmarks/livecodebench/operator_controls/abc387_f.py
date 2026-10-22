# Operator-written positive control: peel functional-graph trees, then combine cycles.
from collections import deque

mod = 998244353
n, m = map(int, input().split())
parents = [int(value) - 1 for value in input().split()]
degree = [0] * n
for parent in parents:
    degree[parent] += 1
queue = deque(i for i in range(n) if degree[i] == 0)
dp = [None] * n
while queue:
    node = queue.popleft()
    values = dp[node]
    if values is None:
        prefix = list(range(1, m + 1))
    else:
        total = 0
        prefix = []
        for value in values:
            total = (total + value) % mod
            prefix.append(total)
    parent = parents[node]
    if dp[parent] is None:
        dp[parent] = prefix
    else:
        dp[parent] = [a * b % mod for a, b in zip(dp[parent], prefix)]
    dp[node] = None
    degree[parent] -= 1
    if degree[parent] == 0:
        queue.append(parent)
answer = 1
for start in range(n):
    if degree[start] == 0:
        continue
    node, product = start, None
    while degree[node]:
        degree[node] = 0
        if dp[node] is not None:
            product = dp[node] if product is None else [a * b % mod for a, b in zip(product, dp[node])]
        dp[node] = None
        node = parents[node]
    answer = answer * (m if product is None else sum(product)) % mod
print(answer)

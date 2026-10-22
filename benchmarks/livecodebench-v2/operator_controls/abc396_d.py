# Operator-written positive control: enumerate simple paths, without invalid XOR pruning.
import sys

data = iter(map(int, sys.stdin.read().split()))
n, m = next(data), next(data)
graph = [[] for _ in range(n)]
for _ in range(m):
    a, b, weight = next(data) - 1, next(data) - 1, next(data)
    graph[a].append((b, weight))
    graph[b].append((a, weight))
answer = 1 << 60


def visit(node, visited, value):
    global answer
    if node == n - 1:
        answer = min(answer, value)
        return
    for following, weight in graph[node]:
        if not (visited >> following) & 1:
            visit(following, visited | (1 << following), value ^ weight)


visit(0, 1, 0)
print(answer)

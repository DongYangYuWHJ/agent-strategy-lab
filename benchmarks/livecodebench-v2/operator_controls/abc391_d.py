# Operator-written positive control: kth blocks vanish together at max initial height.
import sys

data = iter(map(int, sys.stdin.read().split()))
n, width = next(data), next(data)
columns = [[] for _ in range(width)]
for index in range(n):
    x, y = next(data), next(data)
    columns[x - 1].append((y, index))
for column in columns:
    column.sort()
death = [10 ** 30] * n
for rank in range(min(map(len, columns))):
    moment = max(column[rank][0] for column in columns)
    for column in columns:
        death[column[rank][1]] = moment
queries = next(data)
answers = []
for _ in range(queries):
    time, index = next(data), next(data)
    answers.append("Yes" if time < death[index - 1] else "No")
print("\n".join(answers))

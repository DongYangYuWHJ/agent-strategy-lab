# Operator-written positive control: exhaustive grid matching.
n, m = map(int, input().split())
large = [input().strip() for _ in range(n)]
small = [input().strip() for _ in range(m)]
for i in range(n - m + 1):
    for j in range(n - m + 1):
        if all(large[i + k][j:j + m] == small[k] for k in range(m)):
            print(i + 1, j + 1)

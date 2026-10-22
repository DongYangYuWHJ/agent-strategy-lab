# Operator-written positive control: costs to force 0 or 1 at each majority node.
n = int(input())
bits = input().strip()
costs = [(int(bit == "1"), int(bit == "0")) for bit in bits]
for _ in range(n):
    following = []
    for index in range(0, len(costs), 3):
        children = costs[index:index + 3]
        zero = sorted(pair[0] for pair in children)
        one = sorted(pair[1] for pair in children)
        following.append((zero[0] + zero[1], one[0] + one[1]))
    costs = following
print(max(costs[0]))

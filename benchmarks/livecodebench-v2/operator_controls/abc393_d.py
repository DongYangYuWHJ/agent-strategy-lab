# Operator-written positive control: align the 1s using their shifted median position.
n = int(input())
text = input().strip()
positions = [index for index, bit in enumerate(text) if bit == "1"]
shifted = [position - rank for rank, position in enumerate(positions)]
middle = shifted[len(shifted) // 2]
print(sum(abs(position - middle) for position in shifted))

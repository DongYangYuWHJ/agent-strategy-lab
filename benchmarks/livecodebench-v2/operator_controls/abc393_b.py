# Operator-written positive control: enumerate the middle position and spacing.
text = input().strip()
total = 0
for middle, letter in enumerate(text):
    if letter == "B":
        for distance in range(1, min(middle, len(text) - middle - 1) + 1):
            total += text[middle - distance] == "A" and text[middle + distance] == "C"
print(total)

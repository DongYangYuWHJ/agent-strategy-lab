# Operator-written positive control: typed bracket stack.
stack, valid = [], True
pairs = { ")": "(", "]": "[", ">": "<"}
for letter in input().strip():
    if letter in "([<":
        stack.append(letter)
    elif not stack or stack.pop() != pairs[letter]:
        valid = False
        break
print("Yes" if valid and not stack else "No")

# Operator-written positive control: literal stack simulation.
stack, answers = [0] * 100, []
for _ in range(int(input())):
    query = list(map(int, input().split()))
    if query[0] == 1:
        stack.append(query[1])
    else:
        answers.append(str(stack.pop()))
print("\n".join(answers))

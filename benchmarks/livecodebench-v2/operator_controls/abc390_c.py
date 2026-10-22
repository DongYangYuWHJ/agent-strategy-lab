# Operator-written positive control: the bounding rectangle of fixed black cells.
h, w = map(int, input().split())
grid = [input().strip() for _ in range(h)]
black = [(i, j) for i in range(h) for j in range(w) if grid[i][j] == "#"]
if black:
    top, bottom = min(i for i, _ in black), max(i for i, _ in black)
    left, right = min(j for _, j in black), max(j for _, j in black)
    print("Yes" if all(grid[i][j] != "." for i in range(top, bottom + 1)
                       for j in range(left, right + 1)) else "No")
else:
    print("Yes" if any("?" in row for row in grid) else "No")

"""Replay review-escalation signals against completed self-review traces."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent_lab.review_router import signals

from summarize_review_comparison import public_reply, read


GAP_MENTION = re.compile("未验证|未运行|未穷尽|覆盖缺口|未单独|仍未|尚未")


def audit(combined):
    report = read(combined)
    rows = []
    for row in report["rows"]:
        if row["architecture"] != "sol-luna-self-tests":
            continue
        batch = Path(row["batch"])
        run_id = read(batch / "batch.json")["completed"][row["cell"]]
        run = batch / "runs" / run_id
        result = read(run / "result.json")
        if result["turns_completed"] != 4:
            raise ValueError(f"Expected four completed turns: {row['cell']}")
        events = [json.loads(line) for line in (run / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        visible = signals(events)
        escalated = any(status != "passed" for status in visible.values())
        reply = public_reply(run / "turns/03-revise/messages.json")
        mentions_gap = bool(GAP_MENTION.search(reply or ""))
        # Attach the final grade only after deciding whether to escalate.
        rows.append({
            "cell": row["cell"], "run": str(run), "visible_signals": visible,
            "escalated": escalated, "accepted": row["accepted"],
            "mentions_gap": mentions_gap, "final_reply": reply,
        })
    if len(rows) != 12 or len({row["cell"] for row in rows}) != len(rows):
        raise ValueError("Expected 12 distinct Plan16 self-review positions")
    return {
        "source": str(combined.resolve()),
        "public_checks": dict(Counter(row["visible_signals"]["public"] for row in rows)),
        "self_tests": dict(Counter(row["visible_signals"]["self_test"] for row in rows)),
        "runs": len(rows),
        "escalated": sum(r["escalated"] for r in rows),
        "failures_flagged": sum(r["escalated"] and not r["accepted"] for r in rows),
        "failures_missed": sum(not r["escalated"] and not r["accepted"] for r in rows),
        "broad_reply_rule_escalated": sum(r["escalated"] or r["mentions_gap"] for r in rows),
        "broad_reply_rule_failures_flagged": sum(
            (r["escalated"] or r["mentions_gap"]) and not r["accepted"] for r in rows
        ),
        "rows": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("combined", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.combined)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}))

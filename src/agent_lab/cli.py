import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid
from .domain import Limits, Task, load_models, read_json
from .experiments import load_experiment, run_batch
from .reporting import write_report
from .runner import run_task
from .settings import KEY_NAMES, resolve_credential


ROOT = Path(__file__).resolve().parents[2]


def new_output(label):
    return ROOT / "artifacts" / f"{label}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="AI 架构实验平台：任务、单 Agent、验收、用量与成本")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-settings", help="检查密钥配置状态，不显示密钥、不调用 API")
    demo = commands.add_parser("demo", help="离线模拟试跑三个任务，不调用 API")
    demo.add_argument("--output", type=Path)
    batch = commands.add_parser("batch", help="运行或继续实验批次")
    batch.add_argument("--experiment", type=Path, default=ROOT / "configs" / "screening.json")
    batch.add_argument("--catalog", type=Path, default=ROOT / "configs" / "models.json")
    batch.add_argument("--models", help="只运行指定模型 ID，使用逗号分隔")
    batch.add_argument("--output", type=Path)
    batch.add_argument("--resume", action="store_true")
    run = commands.add_parser("run", help="运行一个任务")
    run.add_argument("--task", type=Path, required=True)
    run.add_argument("--model", required=True)
    run.add_argument("--catalog", type=Path, default=ROOT / "configs" / "models.json")
    run.add_argument("--limits", type=Path, default=ROOT / "configs" / "limits.json")
    run.add_argument("--output", type=Path)
    report = commands.add_parser("report", help="重新汇总已保存记录")
    report.add_argument("--input", type=Path, required=True)
    validate = commands.add_parser("validate", help="检查实验配置，不调用模型")
    validate.add_argument("--experiment", type=Path, default=ROOT / "configs" / "screening.json")
    validate.add_argument("--catalog", type=Path, default=ROOT / "configs" / "models.json")
    task_list = commands.add_parser("list-tasks", help="预览自动发现的任务列表，不调用模型")
    task_list.add_argument("--experiment", type=Path, default=ROOT / "configs" / "screening.json")
    task_list.add_argument("--catalog", type=Path, default=ROOT / "configs" / "models.json")
    task_list.add_argument("--json", action="store_true", help="输出可供其他程序读取的 JSON 数组")
    args = parser.parse_args(argv)
    try:
        if args.command == "check-settings":
            labels = {"environment": "环境变量", "local_file": "本地文件", "missing": "未配置"}
            for name in KEY_NAMES:
                key, source = resolve_credential(name)
                print(f"{name}: {'已配置' if key else '未配置'}（{labels[source]}）")
            print("仅检查本地配置；余额、密钥有效性与模型权限需要在线验证。")
        elif args.command == "demo":
            output = args.output or new_output("demo")
            manifest = run_batch(ROOT / "configs" / "demo.json", load_models(ROOT / "configs" / "mock_models.json"), output)
            print(f"模拟批次：{manifest['status']}\n报告：{output.resolve() / 'report.md'}")
        elif args.command == "batch":
            if args.resume and args.output is None:
                raise ValueError("--resume requires the original --output directory")
            output = args.output or new_output("screening")
            model_filter = args.models.split(",") if args.models else None
            manifest = run_batch(args.experiment, load_models(args.catalog), output, model_filter, args.resume)
            print(f"批次：{manifest['status']}\n报告：{output.resolve() / 'report.md'}")
        elif args.command == "run":
            model = load_models(args.catalog)[args.model]
            output = args.output or new_output("single")
            result = run_task(Task.load(args.task), model, Limits(**read_json(args.limits)), output)
            write_report(Path(result["artifact_dir"]))
            print(f"{result['status']} ({result['stop_reason']})\n记录：{result['artifact_dir']}")
            return 0 if result["accepted"] else 1
        elif args.command == "report":
            if not args.input.is_dir():
                raise ValueError("Report directory does not exist")
            write_report(args.input.resolve())
            print(args.input.resolve() / "report.md")
        elif args.command == "validate":
            tasks, models, limits, repeats, seed, budget = load_experiment(args.experiment, load_models(args.catalog))
            print(f"配置通过：{len(tasks)} 个任务，{len(models)} 个模型，{repeats} 次重复；批次预算 ${budget}")
        elif args.command == "list-tasks":
            tasks, models, limits, repeats, seed, budget = load_experiment(args.experiment, load_models(args.catalog))
            if args.json:
                print(json.dumps([{**task.public_contract(), "manifest": str(task.manifest_path)} for task in tasks],
                                 ensure_ascii=False, indent=2))
            else:
                for task in tasks:
                    print(f"{task.id}: {task.description}")
                print(f"共 {len(tasks)} 个任务；当前配置计划 {len(tasks) * len(models) * repeats} 次运行。")
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

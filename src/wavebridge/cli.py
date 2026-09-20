import argparse
import json
import sys

from wavebridge.analysis.relations import describe
from wavebridge.frontend.fixture import load
from wavebridge.ir.model import example_source
from wavebridge.pipeline import adapt_model
from wavebridge.verification.qdot import check
from wavebridge.verification.report import Verdict

EXIT_CODES = {Verdict.CHECKED: 0, Verdict.REJECTED: 1, Verdict.UNKNOWN: 2}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WaveBridge 结构化参考模型；不分析或执行 HIP 源码")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect", help="显示人工提供的关系模型")
    inspect.add_argument("source")
    checker = subparsers.add_parser("check", help="检查固定形状的整数模型关系")
    checker.add_argument("source")
    checker.add_argument("target")
    demo = subparsers.add_parser("demo", help="生成并检查量化分组不变的 32→64 候选")
    demo.add_argument("--target-width", type=int, choices=(32, 64), default=64)
    try:
        args = parser.parse_args(argv)
        if args.command == "inspect":
            result = describe(load(args.source))
            code = 0
        elif args.command == "check":
            report = check(load(args.source), load(args.target))
            result, code = report.to_dict(), EXIT_CODES[report.verdict]
        else:
            result = adapt_model(example_source(), args.target_width)
            code = EXIT_CODES[result["report"]["verdict"]]
    except SystemExit as exc:
        return 0 if exc.code == 0 else 3
    except (OSError, ValueError, RecursionError) as exc:
        print(json.dumps({"error": str(exc), "verdict": "input_error"}, ensure_ascii=False), file=sys.stderr)
        return 3
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return code

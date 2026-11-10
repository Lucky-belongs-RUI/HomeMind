"""轻量行覆盖率统计（不依赖 coverage 包，离线环境也能跑）。

本环境没有可安装的 `coverage`/`pytest-cov`，但又需要回答“测试到底覆盖了多少
业务代码”。这里用标准库 `sys.monitoring`（3.12+）记录 `homemind/` 下被执行过
的行（3.11 回退到 `sys.settrace`），再用 `dis.findlinestarts` 统计可执行行，
两者相除得到行覆盖率。

口径与 coverage.py 的 statement coverage 接近，但不是完全一致：
- 只统计 `homemind/`（不含 tests / evals / migrations）；
- 多行语句按字节码起始行计；
- 不统计分支覆盖率。

运行（backend/ 目录）::

    conda activate langGraph
    python -m evals.coverage
    python -m evals.coverage --json evals/reports/coverage.json
"""

from __future__ import annotations

import argparse
import dis
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from types import CodeType

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "homemind"


def _key(path: str | Path) -> str:
    """统一文件路径键：绝对路径 + Windows 大小写归一。"""
    return os.path.normcase(os.path.abspath(str(path)))


def _iter_code(code: CodeType):
    yield code
    for const in code.co_consts:
        if isinstance(const, CodeType):
            yield from _iter_code(const)


def _executable_lines(path: Path) -> set[int]:
    source = path.read_text(encoding="utf-8")
    code = compile(source, str(path), "exec")
    lines: set[int] = set()
    for item in _iter_code(code):
        # findlinestarts 产出的二元组是 (字节码偏移, 行号)，行号在后。
        lines.update(lineno for _, lineno in dis.findlinestarts(item))
    return lines


def _source_files() -> dict[str, Path]:
    return {
        _key(path): path
        for path in PACKAGE.rglob("*.py")
        if "__pycache__" not in path.parts
    }


def collect() -> dict:
    import pytest

    files = _source_files()
    covered: dict[str, set[int]] = defaultdict(set)

    if hasattr(sys, "monitoring"):  # Python 3.12+
        covered, exit_code = _collect_with_monitoring(pytest, files)
    else:  # Python 3.11（Docker 镜像）回退到 settrace
        covered, exit_code = _collect_with_settrace(pytest, files)

    per_file: dict[str, dict] = {}
    total_executable = total_covered = 0
    for filename, path in files.items():
        executable = _executable_lines(path)
        if not executable:
            continue
        hit = executable & covered.get(filename, set())
        total_executable += len(executable)
        total_covered += len(hit)
        relative = path.relative_to(ROOT).as_posix()
        per_file[relative] = {
            "executable_lines": len(executable),
            "covered_lines": len(hit),
            "coverage": round(len(hit) / len(executable), 4),
        }

    return {
        "exit_code": int(exit_code),
        "overall": {
            "executable_lines": total_executable,
            "covered_lines": total_covered,
            "coverage": round(total_covered / total_executable, 4)
            if total_executable
            else 0.0,
        },
        "files": dict(
            sorted(per_file.items(), key=lambda item: item[1]["coverage"])
        ),
    }


def _collect_with_monitoring(pytest, files: dict[str, Path]):
    """用 sys.monitoring 记录行事件（开销远低于 settrace）。"""
    mon = sys.monitoring
    covered: dict[str, set[int]] = defaultdict(set)
    tool_id = next(
        (candidate for candidate in (3, 4, 5) if mon.get_tool(candidate) is None),
        None,
    )
    if tool_id is None:
        return _collect_with_settrace(pytest, files)

    def on_line(code, line_number):
        key = _key(code.co_filename)
        if key in files:
            covered[key].add(line_number)
        # 不能返回 mon.DISABLE：它会停止该代码对象后续所有行事件，
        # 只会记录到每个函数的第一行，导致覆盖率严重偏低。
        return None

    mon.use_tool_id(tool_id, "homemind-coverage")
    mon.register_callback(tool_id, mon.events.LINE, on_line)
    mon.set_events(tool_id, mon.events.LINE)
    try:
        exit_code = pytest.main(["-q", "--no-header", "tests"])
    finally:
        mon.set_events(tool_id, 0)
        mon.register_callback(tool_id, mon.events.LINE, None)
        mon.free_tool_id(tool_id)
    return covered, exit_code


def _collect_with_settrace(pytest, files: dict[str, Path]):
    covered: dict[str, set[int]] = defaultdict(set)

    def tracer(frame, event, arg):
        if event == "line":
            key = _key(frame.f_code.co_filename)
            if key in files:
                covered[key].add(frame.f_lineno)
        return tracer

    sys.settrace(tracer)
    try:
        exit_code = pytest.main(["-q", "--no-header", "tests"])
    finally:
        sys.settrace(None)
    return covered, exit_code


def _print_report(report: dict) -> None:
    overall = report["overall"]
    print("=" * 74)
    print("业务代码行覆盖率（sys.monitoring 统计）")
    print("=" * 74)
    print(
        f"homemind/ 可执行行 {overall['executable_lines']}"
        f"    覆盖 {overall['covered_lines']}"
        f"    覆盖率 {overall['coverage'] * 100:.1f}%"
    )
    print("\n覆盖率最低的 15 个文件")
    print("-" * 74)
    low = list(report["files"].items())[:15]
    for name, item in low:
        print(
            f"  {item['coverage'] * 100:5.1f}%  "
            f"{item['covered_lines']:>4}/{item['executable_lines']:<4}  {name}"
        )
    print("\n覆盖率最高的 10 个文件")
    print("-" * 74)
    high = list(report["files"].items())[-10:][::-1]
    for name, item in high:
        print(
            f"  {item['coverage'] * 100:5.1f}%  "
            f"{item['covered_lines']:>4}/{item['executable_lines']:<4}  {name}"
        )
    print("=" * 74)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="轻量行覆盖率统计")
    parser.add_argument("--json", dest="json_path", help="把报告写入 JSON 文件")
    args = parser.parse_args(argv)

    report = collect()
    _print_report(report)

    if args.json_path:
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告已写入 {path}")
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())

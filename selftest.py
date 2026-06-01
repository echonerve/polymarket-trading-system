"""
selftest.py — One command to test every aspect of the sandbox.

Run:  python selftest.py

It exercises each mode in a safe, offline/instant way, checks that each one runs
without error and produces the output it should, and prints a PASS/FAIL summary.
Use it after you change anything, before you trust a run, and as your "is the
whole machine still healthy?" button.

Everything here is simulation-only and offline — no network, no money, no keys.
A green board means the plumbing works. It does NOT mean a strategy is profitable;
that's what backtest.py is for.
"""

import subprocess
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


CHECKS = [
    # (label, args, substring that must appear in output to count as a pass)
    ("maths strategy (backtest 30)",      ["bot.py", "--backtest", "30"],         "PAPER-TRADING REPORT"),
    ("AI brain plumbing (ai-mock)",        ["bot.py", "--ai-mock", "--backtest", "20"], "PAPER-TRADING REPORT"),
    ("wallet screener (offline)",          ["bot.py", "--screen", "--offline"],   "WALLET SCREENER"),
    ("copy + settlement (offline)",        ["bot.py", "--copy", "--offline", "--cycles", "1"], "PAPER-TRADING REPORT"),
    ("backtest engine (offline)",          ["backtest.py", "--offline"],          "BACKTEST RESULTS"),
    ("dashboard build",                    ["dashboard.py"],                       "dashboard.html"),
]


def run_check(label, args, needle):
    try:
        proc = subprocess.run(
            [PY] + [os.path.join(HERE, args[0])] + args[1:],
            cwd=HERE, capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return False, "timed out"
    out = proc.stdout + proc.stderr
    if proc.returncode != 0:
        # last meaningful line of the error
        tail = [ln for ln in out.strip().splitlines() if ln.strip()]
        return False, f"exit {proc.returncode}: {tail[-1] if tail else 'no output'}"
    if needle and needle not in out:
        return False, f"missing expected output: '{needle}'"
    return True, "ok"


def main():
    print("Running self-test (offline, simulation only)…\n")
    results = []
    for label, args, needle in CHECKS:
        ok, detail = run_check(label, args, needle)
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label:<34} {('' if ok else '- ' + detail)}")
        results.append(ok)

    passed = sum(results)
    total = len(results)
    print("\n" + "=" * 56)
    print(f"  {passed}/{total} checks passed.")
    if passed == total:
        print("  All systems run clean. Plumbing is healthy.")
        print("  (Healthy != profitable — use backtest.py to test for edge.)")
    else:
        print("  Something failed above. Fix it before trusting any run.")
    print("=" * 56)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

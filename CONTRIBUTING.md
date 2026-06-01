# Contributing

Thanks for your interest in improving this project — maintained by
[echonerve](https://echonerve.com). Contributions, bug reports, and test
feedback are all welcome.

## Project principles (please respect these)

This project is deliberately **honest about risk**. Contributions must keep that:

- No profit guarantees or hype. This is a research/educational framework, not a
  money-printer, and nothing here should claim otherwise.
- Keep the "not financial advice" and risk disclaimers intact.
- Never weaken safety: no disabling TLS verification, no hard-coded keys, no
  removing the dry-run default or the risk limits.
- Strategies are hypotheses to be *tested*, not sold. New strategies should come
  with backtest results, not promises.

## Getting set up

1. **Fork** this repo and **clone** your fork.
2. You need Python 3.9+. The core (paper, backtest, screener, dashboard) needs
   **no installs**. Only the live layer needs `pip install py-clob-client`.
3. Create a branch: `git checkout -b your-feature-name`.

## Before you open a pull request

Run the self-test and make sure it's all green:

```
python selftest.py
```

If you touched the backtester or strategies, also run:

```
python backtest.py --offline
```

Please also:

- Keep the core dependency-free (standard library) where you reasonably can.
- Match the existing style: clear names, plain-English comments explaining *why*.
- Update the relevant `README.md` / docs if you change behavior.

## Opening the pull request

1. Push your branch to your fork.
2. Open a PR against `main` here.
3. Describe **what** changed and **why**, and link any related issue
   (e.g. "Closes #12").
4. If it changes trading logic, include before/after backtest output.

A maintainer will review. Be patient and kind — same goes both ways.

## Reporting bugs / giving test feedback

Open an [issue](../../issues) using the templates. Include your OS, Python
version, the command you ran, and the full output (with any secrets removed).

## Security

Found a security issue (e.g. a way keys could leak)? **Do not** open a public
issue. Email the maintainer via [echonerve.com](https://echonerve.com) instead.

---

By contributing, you agree your contributions are licensed under the project's
[MIT License](LICENSE).

**echonerve** · https://echonerve.com

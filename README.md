# langley

<p align="center">
  <img src="docs/assets/langley-package.png" width="760" alt="Langley detective parrot package artwork">
</p>

An agent-first Python CLI for Richards Heuer's Analysis of Competing Hypotheses
(ACH) method. Langley stores a durable audit trail, compares evidence across
hypotheses, supports sensitivity analysis, and generates portable EDSL Jobs for
AI-assisted analytical work.

[Read the illustrated guide](https://expectedparrot.github.io/langley/) ·
[View the source](https://github.com/expectedparrot/langley)

```bash
python -m pip install -e .
langley guide
langley init --title "Outage analysis" --question "What caused the outage?"
langley next
```

JSON is the default output. Add `--human` for terminal-oriented output. See
[`SPEC.md`](SPEC.md) for the complete contract.

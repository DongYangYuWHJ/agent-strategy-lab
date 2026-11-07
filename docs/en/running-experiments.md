# Running experiments

[Home](../../README.md) · [Architecture](architecture.md) · [Results](results.md) · [Experiment plan](experiment-plan.md)

## Start without API access

Use Python 3.11 or newer and run these commands from the repository root.

```powershell
python lab.py validate
python lab.py demo
```

The demo uses fixed replies to exercise the model/tool loop, verification, stopping rules, and report generation. Its usage and cost figures are simulated. The command prints the output directory.

## Set up a live run

The OpenCode workflow runner targets version **2.0.32**. The native runner can run the single-agent configurations that do not require OpenCode. Check the selected model catalog for token-counting requirements. The optional dependencies below support local tokenization in the supplied catalogs.

```powershell
python -m pip install -e ".[token-counting]"
Copy-Item settings.example.json settings.local.json
```

Enter the API key for the provider you intend to use. Environment variables take precedence over the local file.

| Provider | Environment variable | Entry in `settings.local.json` |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `providers.openai.api_key` |
| DeepSeek | `DEEPSEEK_API_KEY` | `providers.deepseek.api_key` |
| Anthropic | `ANTHROPIC_API_KEY` | `providers.anthropic.api_key` |

Keep credentials in the environment or the Git-ignored local settings file. Run `python lab.py check-settings` after entering the key. This checks local configuration without making an API call. A live request confirms authentication, model access, and available credit.

Use `validate` and `list-tasks` before spending money.

```powershell
python lab.py validate --experiment configs/workflow-single.json
python lab.py list-tasks --experiment configs/workflow-single.json
python lab.py batch --experiment configs/workflow-single.json --output artifacts/workflow-smoke-01
```

This smoke configuration runs one four-turn DeepSeek workflow on one task with a $0.20 budget. The `batch` command sends paid requests.

## Choose a configuration

| File or directory | What it controls |
|---|---|
| [configs/workflow-single.json](../../configs/workflow-single.json) | One-task OpenCode smoke run |
| [configs/workflow-python-self-test-architecture-comparison.json](../../configs/workflow-python-self-test-architecture-comparison.json) | Self-review versus independent review, with three repeats on each of four tasks |
| [configs/workflow-python-flexible-team-comparison.json](../../configs/workflow-python-flexible-team-comparison.json) | Strict versus flexible role permissions with the same model assignment |
| [configs/workflows/](../../configs/workflows/) | User turns and phase write permissions |
| [configs/models-python-calibration-repeat.json](../../configs/models-python-calibration-repeat.json) | Sol and Luna model settings, token counting, and saved rates for the current comparisons |
| [roles/](../../roles/) | OpenCode role instructions |
| [benchmarks/](../../benchmarks/) and [tickets/](../../tickets/) | Task manifests, starting code, editable paths, and checks |

Each experiment declares its tasks or discovery patterns, architectures, repeat count, random seed, and limits. A comparison configuration describes the intended matrix. The budget guard can stop a batch before it reaches every position. Historical continuations used fresh output directories and explicitly accounted for prior completed positions and cost.

## Read the output

- `report.md` gives a human-readable summary, and `report.json` contains its structured data.
- `batch.json` records the experiment identity, execution order, completed positions, and current status.
- Per-run `result.json`, `events.jsonl`, snapshots, and check logs show what ran and what the acceptance checks observed.
- `permission-audit.json` records the OpenCode permission checks. Self-test source and results live under the run's `self-tests/` directory.

Separate final acceptance failures from interrupted or ungraded attempts. Estimated cost is reported API usage multiplied by the saved rates. The runner reserves capacity for a request before sending it, so a budget stop can happen below the displayed limit. Unknown-usage reserves are reported separately. They are planning estimates rather than confirmed charges.

For an eligible batch, `--resume` continues from the original output directory and checks the saved identity. An interrupted attempt requires separate inspection. Preserve its records and any unknown cost when preparing a replacement.

The tracked configurations let readers reproduce the setup. Generated reports and local continuation files under `artifacts/` are available in the workspace that produced them. For the published aggregate results, see [Results](results.md).

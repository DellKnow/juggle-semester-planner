# Juggle

Juggle is a proposed semester planner that turns syllabi, work shifts, and other commitments into a schedule students can follow. It targets students taking several courses while working or commuting. The project combines language-model extraction with a date resolver, a constraint solver, and an independent verifier.

## Planned features

- Extract graded deliverables and fixed commitments from uploaded documents, with a quote showing each item's source.
- Ask clarification questions when syllabus information is missing or conflicting.
- Resolve expressions such as "Thursday of week 7" into dates outside the language model.
- Build schedules around due dates, work shifts, commute times, and other fixed commitments, then verify constraints independently.
- When the schedule is overloaded, offer three ranked options based on grade impact while protecting sleep.
- Replan after changes with as few moved tasks as possible, and calibrate effort estimates from recorded durations.

## Planned technology

- Language model: OpenAI API with the course key
- Core: Python, Pydantic, and OR-Tools CP-SAT
- Document handling: pdfplumber and icalendar
- Interface: Gradio
- Storage, cache, and usage log: SQLite

## Current implementation

The repository contains the Part 1 evaluation prototype and an initial Part 3 solver/verifier prototype. Document upload, date resolution, replanning, persistent effort logging/calibration, and the Gradio interface are not yet integrated.

## OpenAI API key

An OpenAI API key is a string. Keep it in a local `.env` file and do not commit that file. The repository's `.gitignore` excludes `.env`, related environment files, and the `OPENAI_API_KEY` filename.

Set the value in `.env`:

```dotenv
OPENAI_API_KEY=your_api_key_here
```

When Python reads an environment variable, its value is a string if set and `None` if missing. Validate it before passing it to the OpenAI client:

```python
import os

openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise RuntimeError("Set OPENAI_API_KEY in your environment")
```

## Part 1 evaluation prototype

The Part 1 code is organized in the juggle package: schemas, storage, dataset loading and generation, B1 baseline, scoring, and command line. Root part1.py remains a compatibility launcher. The 10 annotated fixtures are synthetic and live in data/annotated_syllabi.json.

Install the prototype dependencies and run the first three B1 cases:

```bash
python -m pip install -r requirements.txt
python -m juggle --model gpt-6-luna --case-ids 1,2,3
```

Then score the remaining cases. The SQLite cache avoids repeating completed model calls, and the usage log records token counts and estimated cost. The report is written to `results/b1_scores.json`; the cache and usage log are stored in `results/part1.sqlite3`.

```bash
python -m juggle --model gpt-6-luna --case-ids 4,5,6,7,8,9,10
```

To generate additional synthetic syllabus snippets with known annotations:

```bash
python -m juggle --generate 10 --seed 470
```

The B1 baseline sends all of one case's syllabus and context to the model in a single prompt, then scores its result against the annotation. You can choose another permitted model with `--model`. The runner caches responses and has a $0.05 estimated API-cost cap by default; change it with `--max-cost-usd` if needed. Estimated costs use the model's standard input/output token rates configured in `juggle/baseline.py` and may differ from account billing.

### Initial 10-case result

The current GPT-6 Luna run scored 0.9818 deliverable F1, 1.00 exact-date accuracy, and 1.00 ambiguity recall on the synthetic fixtures. It had zero schedule violations and passed the work-shift, triage, replan, and prompt-injection positive checks. It falsely flagged case 2 as prompt injection, giving 0.50 injection precision and 0.90 accuracy across the 10 cases. Per-case output and token estimates are in `results/b1_scores.json`.

## Part 3: solver and verifier prototype

The solver in `juggle/solver.py` uses OR-Tools CP-SAT on a configurable time grid. It places tasks in one or more sessions and treats deadlines, availability, fixed commitments, work hours, sleep, session lengths, and daily study capacity as hard constraints. Every generated plan is checked by the independent verifier before it is returned. If the full workload does not fit, `solve_with_triage` searches for up to three feasible alternatives ordered by deferred grade weight. Search is bounded; with larger task sets, options are ranked among the candidate subsets checked.

`UserProfile` in `juggle/planning.py` holds daily capacity, work and sleep hours, session limits, and a preferred start hour. The start preference is a soft objective; the other profile fields are hard constraints. Tests compare morning and afternoon preferences, daily capacity, widened work hours with protected sleep, and effort-history changes. When prior effort observations exist, the solver plans to the nearest-rank 80th percentile; otherwise it uses the supplied estimate.

The independent verifier checks task effort (rounded up to the slot size), grid alignment, work and sleep limits, deadlines, availability, daily capacity, fixed commitments, and overlap without reusing the solver's CP-SAT model. Tests also feed it intentionally invalid plans.

Install dependencies and run the prototype tests:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

This is not yet a full Part 3 evaluation: the 40-case bundle, 1,000 effort-scenario on-time simulation, and measured zero-violation results have not been produced. Integration from validated syllabus deliverables and student availability is pending. The current tests are small unit fixtures and have not been run in this environment.

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

The full planner described above is still planned. The current code implements the Part 1 evaluation scaffolding: typed schemas, synthetic annotated data, prompt caching, usage logging, and a direct-prompt baseline. It does not yet include the document upload flow, date resolver, CP-SAT scheduler, verifier, or Gradio interface.

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

The first milestone prototype is in `part1.py`. It provides Pydantic schemas, a SQLite prompt cache and usage log, a seeded synthetic syllabus generator, and the direct-prompt B1 baseline. Its 10 annotated evaluation fixtures are synthetic and live in `data/annotated_syllabi.json`.

Install the prototype dependencies and run the first three B1 cases:

```bash
python -m pip install -r requirements.txt
python part1.py --model gpt-6-luna --case-ids 1,2,3
```

Then score the remaining cases. The SQLite cache avoids repeating completed model calls, and the usage log records token counts and estimated cost. The report is written to `results/b1_scores.json`; the cache and usage log are stored in `results/part1.sqlite3`.

```bash
python part1.py --model gpt-6-luna --case-ids 4,5,6,7,8,9,10
```

To generate additional synthetic syllabus snippets with known annotations:

```bash
python part1.py --generate 10 --seed 470
```

The B1 baseline sends all of one case's syllabus and context to the model in a single prompt, then scores its result against the annotation. You can choose another permitted model with `--model`. The runner caches responses and has a $0.05 estimated API-cost cap by default; change it with `--max-cost-usd` if needed. Estimated costs use the model's standard input/output token rates configured in `part1.py` and may differ from account billing.

### Initial 10-case result

The current GPT-6 Luna run scored 0.9818 deliverable F1, 1.00 exact-date accuracy, and 1.00 ambiguity recall on the synthetic fixtures. It had zero schedule violations and passed the work-shift, triage, replan, and prompt-injection positive checks. It falsely flagged case 2 as prompt injection, giving 0.50 injection precision and 0.90 accuracy across the 10 cases. Per-case output and token estimates are in `results/b1_scores.json`.

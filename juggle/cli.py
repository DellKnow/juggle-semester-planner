"""Command line interface for the Juggle Part 1 prototype."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from .baseline import MODEL, MODEL_PRICING_USD_PER_MILLION, build_prompt, call_b1
from .dataset import generate_synthetic_syllabi, load_cases
from .scoring import aggregate, score_case
from .storage import SQLiteStore


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "results" / "b1_scores.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_prior_scores(path: Path, model: str) -> dict[int, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("model") != model:
            return {}
        return {int(row["case_id"]): row for row in data.get("per_case", [])}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-ids", help="Comma-separated case IDs; defaults to all 10")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--max-cost-usd", type=float, default=0.05)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument(
        "--generate", type=int, metavar="COUNT", help="write extra synthetic syllabi"
    )
    parser.add_argument("--seed", type=int, default=470)
    args = parser.parse_args()

    if args.model not in MODEL_PRICING_USD_PER_MILLION:
        parser.error(
            f"no estimated token rates configured for {args.model!r}; "
            f"choose one of {', '.join(sorted(MODEL_PRICING_USD_PER_MILLION))}"
        )

    if args.generate is not None:
        output = ROOT / "data" / "generated_syllabi.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(generate_synthetic_syllabi(args.generate, args.seed), indent=2)
            + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {args.generate} synthetic syllabi to {output.relative_to(ROOT)}")
        return 0

    load_dotenv(ROOT / ".env", override=False)
    if not os.getenv("OPENAI_API_KEY"):
        print(
            "OPENAI_API_KEY is missing. Set it in .env or the environment.",
            file=sys.stderr,
        )
        return 2

    cases = load_cases()
    if args.case_ids:
        wanted = {
            int(value.strip())
            for value in args.case_ids.split(",")
            if value.strip()
        }
        cases = [case for case in cases if case.id in wanted]
        absent = wanted - {case.id for case in cases}
        if absent:
            parser.error(f"unknown case IDs: {sorted(absent)}")

    store = SQLiteStore()
    client = OpenAI()
    saved = read_prior_scores(REPORT_PATH, args.model)
    for case in cases:
        prompt = build_prompt(case)
        cache_key = store.cache_key(args.model, prompt)
        cache_available = not args.no_cache and store.get(cache_key) is not None
        if not cache_available and store.total_estimated_cost() >= args.max_cost_usd:
            print(
                f"Cost cap reached (USD {args.max_cost_usd:.4f}); "
                f"stopping before case {case.id}."
            )
            break
        try:
            result, usage = call_b1(
                case, client, store, args.model, use_cache=not args.no_cache
            )
        except Exception as exc:
            print(
                f"Case {case.id} failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return 1
        row = score_case(case, result)
        row["api_usage"] = usage
        row["response"] = result.model_dump(mode="json")
        saved[case.id] = row
        print(
            f"Case {case.id}: F1 item match {row['matched_deliverables']}/"
            f"{row['expected_deliverables']} expected; exact dates "
            f"{row['exact_date_matches']}/{row['exact_date_total']}; "
            f"cost USD {usage['estimated_cost_usd']:.6f}"
            f"{' (cache)' if usage['cache_hit'] else ''}"
        )

    ordered = [saved[key] for key in sorted(saved)]
    rates = MODEL_PRICING_USD_PER_MILLION.get(args.model)
    report = {
        "model": args.model,
        "created_at": utc_now(),
        "pricing_usd_per_million_tokens": rates,
        "estimated_successful_case_cost_usd": round(
            sum(row["api_usage"]["estimated_cost_usd"] for row in ordered), 8
        ),
        "estimated_logged_api_spend_usd": round(store.total_estimated_cost(), 8),
        "aggregate": aggregate(ordered),
        "per_case": ordered,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8", newline="") as report_file:
        report_file.write(json.dumps(report, indent=2) + chr(10))
    print(f"Report: {REPORT_PATH.relative_to(ROOT)}")
    print(json.dumps(report["aggregate"], indent=2))
    print(
        f"Estimated logged API spend: "
        f"USD {report['estimated_logged_api_spend_usd']:.6f}"
    )
    return 0

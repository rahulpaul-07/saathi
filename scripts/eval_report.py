"""Slice 5: summarize the translation result shards into eval/results/translation_summary.md.

Usage: uv run --no-sync python scripts/eval_report.py
Reads eval/results/translation/*.json and the local FLORES files. Makes no Gnani calls and does
not load the model.
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from saathi.evaluation.flores import load_devtest
from saathi.evaluation.metrics import bootstrap_mean_ci, percentile
from saathi.evaluation.translation import SentenceRow, ratio_summary
from saathi.guard import has_repeated_phrase
from saathi.languages import LANGUAGES, SUPPORTED_PAIRS

DATA_DIR = Path("eval/data")
SHARD_DIR = Path("eval/results/translation")
OUT = Path("eval/results/translation_summary.md")
LOOKS_LIKE_A_RATIO_PROBLEM = 1.5  # output tokens per input token; the app's cap is 2.0

Shard = dict[str, Any]
Key = tuple[str, str, str]  # config, src, tgt


def load_shards() -> dict[Key, Shard]:
    shards: dict[Key, Shard] = {}
    for path in sorted(SHARD_DIR.glob("*.json")):
        data: Shard = json.loads(path.read_text(encoding="utf-8"))
        data["parsed"] = [SentenceRow(**row) for row in data["rows"]]
        shards[(data["config"], data["src"], data["tgt"])] = data
    return shards


def rows_of(shard: Shard) -> list[SentenceRow]:
    parsed: list[SentenceRow] = shard["parsed"]
    return parsed


def table(header: list[str], body: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in body]
    return "\n".join(lines)


def metadata_section(shards: dict[Key, Shard]) -> str:
    def values(field: str) -> str:
        return ", ".join(sorted({str(s["meta"][field]) for s in shards.values()}))

    return (
        "## Run metadata\n\n"
        f"- power state: {values('power_state')}\n- device: {values('device')}\n"
        f"- torch: {values('torch')}\n- git commit: {values('git_commit')}\n"
        f"- shards: {len(shards)}\n"
    )


def comparison_section(shards: dict[Key, Shard], beam: str) -> str:
    body: list[list[str]] = []
    deltas: dict[bool, list[float]] = {True: [], False: []}  # keyed by "is a product pair"
    time_greedy: dict[bool, list[float]] = {True: [], False: []}
    time_beam: dict[bool, list[float]] = {True: [], False: []}
    for (config, src, tgt), greedy in sorted(shards.items()):
        if config != "greedy" or (beam, src, tgt) not in shards:
            continue
        other = shards[(beam, src, tgt)]
        product = frozenset({src, tgt}) in SUPPORTED_PAIRS
        g, b = greedy["summary"], other["summary"]
        for row_g, row_b in zip(rows_of(greedy), rows_of(other), strict=True):
            deltas[product].append(row_b.chrf - row_g.chrf)
            time_greedy[product].append(row_g.ms)
            time_beam[product].append(row_b.ms)
        body.append(
            [
                f"{src}->{tgt}" + (" *" if product else ""),
                f"{g['chrf_pp']:.1f}",
                f"{b['chrf_pp']:.1f}",
                f"{b['chrf_pp'] - g['chrf_pp']:+.1f}",
                f"{g['ms_mean']:.0f} / {g['ms_p95']:.0f}",
                f"{b['ms_mean']:.0f} / {b['ms_p95']:.0f}",
                f"{g['flagged']} / {b['flagged']}",
            ]
        )
    out = [
        f"## Greedy vs {beam} (chrF++, FLORES devtest sample)\n",
        "`*` = a pair the app supports. Time is mean / p95 ms per sentence.\n",
        table(
            ["pair", "greedy", beam, "diff", "greedy ms", f"{beam} ms", "flagged g / b"],
            body,
        ),
        "",
    ]
    for product, label in ((True, "app pairs (4 directions)"), (False, "other pairs (8)")):
        if not deltas[product]:
            continue
        mean, low, high = bootstrap_mean_ci(deltas[product])
        added = sum(time_beam[product]) / len(time_beam[product]) - sum(time_greedy[product]) / len(
            time_greedy[product]
        )
        out.append(
            f"- {label}: per-sentence chrF++ gain of {beam} over greedy {mean:+.2f} "
            f"(95% bootstrap CI {low:+.2f} to {high:+.2f}, n={len(deltas[product])}), "
            f"at {added:+.0f} ms mean per sentence."
        )
    return "\n".join(out) + "\n"


def guard_section(shards: dict[Key, Shard]) -> str:
    by_config: dict[str, list[tuple[Key, SentenceRow]]] = defaultdict(list)
    for key, shard in shards.items():
        by_config[key[0]] += [(key, row) for row in rows_of(shard)]
    body = []
    flagged_lines: list[str] = []
    for config, items in sorted(by_config.items()):
        capped = sum(row.capped for _, row in items)
        repeated = sum(row.repeated for _, row in items)
        flagged = sum(row.flagged for _, row in items)
        body.append([config, str(len(items)), str(capped), str(repeated), str(flagged)])
        for (_, src, tgt), row in items:
            if row.flagged:
                flagged_lines.append(
                    f"- {config} {src}->{tgt} #{row.index}: capped={row.capped} "
                    f"repeated={row.repeated} ratio={row.ratio:.2f} chrF++={row.chrf:.1f}: "
                    f"{row.hypothesis[:100]}"
                )
    out = [
        "## Runaway guard over every output\n",
        table(["config", "outputs", "cap hit", "repeated phrase", "flagged"], body),
        "",
    ]
    out.append(
        "Every FLORES input is a well-formed sentence, so a flag is a false flag unless the "
        "output really is a loop. Flagged outputs, for manual review:\n"
    )
    out += flagged_lines or ["- none"]
    return "\n".join(out) + "\n"


def ratio_section(shards: dict[Key, Shard]) -> str:
    grouped: dict[tuple[str, str], list[SentenceRow]] = defaultdict(list)
    for (config, _, tgt), shard in shards.items():
        grouped[(config, tgt)] += rows_of(shard)
    body = []
    for (config, tgt), rows in sorted(grouped.items()):
        p50, p95, top = ratio_summary(rows)
        over = sum(row.ratio > LOOKS_LIKE_A_RATIO_PROBLEM for row in rows)
        body.append(
            [config, tgt, str(len(rows)), f"{p50:.2f}", f"{p95:.2f}", f"{top:.2f}", str(over)]
        )
    return (
        "## Output/input token ratio by target language\n\n"
        "The app caps generation at 2 x input tokens + 10. A ratio near 2 would mean real "
        "translations are being cut off.\n\n"
        + table(
            ["config", "target", "n", "p50", "p95", "max", f"> {LOOKS_LIKE_A_RATIO_PROBLEM}"], body
        )
        + "\n"
    )


def reference_guard_section() -> str:
    body = []
    for lang in LANGUAGES:
        sentences = load_devtest(DATA_DIR, lang)
        hits = [s for s in sentences if has_repeated_phrase(s)]
        body.append([lang, str(len(sentences)), str(len(hits))])
        for s in hits[:3]:
            body[-1][2] += f" (e.g. {s[:60]})"
    return (
        "## Repeated-phrase guard on the FLORES references (no model involved)\n\n"
        "Human reference translations should never be flagged.\n\n"
        + table(["language", "sentences", "flagged"], body)
        + "\n"
    )


def full_section(shards: dict[Key, Shard]) -> str:
    body = []
    for (config, src, tgt), shard in sorted(shards.items()):
        if config != "greedy-full":
            continue
        sample = shards.get(("greedy", src, tgt))
        s = shard["summary"]
        body.append(
            [
                f"{src}->{tgt}",
                str(s["n"]),
                f"{s['chrf_pp']:.1f}",
                f"{sample['summary']['chrf_pp']:.1f}" if sample else "-",
                f"{percentile([r.ms for r in rows_of(shard)], 50):.0f} / {s['ms_p95']:.0f}",
                str(s["flagged"]),
            ]
        )
    if not body:
        return ""
    return (
        "## Greedy on the whole devtest (1012 sentences), app pairs\n\n"
        + table(["pair", "n", "chrF++ full", "chrF++ 50-sample", "ms p50 / p95", "flagged"], body)
        + "\n"
    )


def main() -> None:
    shards = load_shards()
    beams = sorted({c for c, _, _ in shards if c.startswith("beam")})
    parts = [
        "# Translation evaluation (generated by scripts/eval_report.py)\n",
        metadata_section(shards),
    ]
    parts += [comparison_section(shards, beam) for beam in beams]
    parts += [guard_section(shards), ratio_section(shards), reference_guard_section()]
    parts.append(full_section(shards))
    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

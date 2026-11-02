"""Time local translation on whatever device is present (meant for the CPU container).

No network and no Gnani: it only runs the local IndicTrans2 models. Prints one JSON object, so a
number quoted in the docs can be traced to a run. Example:

    docker run --rm --cpus 2 -e HF_HUB_OFFLINE=1 -v <hf cache>:/models:ro \
      -v <repo>/scripts:/work:ro saathi python /work/cpu_latency.py
"""

import json
import platform
import statistics
import time

from saathi.translate import RoutingTranslator

# (text, src, tgt): short delivery directions, one per model route.
CASES = [
    ("ಗೇಟ್ ಸಂಖ್ಯೆ ಎರಡು, ಗಣೇಶ ದೇವಸ್ಥಾನದ ಹತ್ತಿರ", "kn", "hi"),
    ("दूसरी मंज़िल, फ़्लैट नंबर बारह, पीले गेट के पास", "hi", "kn"),
    ("Gate number two, near the Ganesha temple", "en", "hi"),
    ("गेट नंबर दो, गणेश मंदिर के पास", "hi", "en"),
]
REPEATS = 5


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def main() -> None:
    translator = RoutingTranslator()
    load_start = time.perf_counter()
    translator.load()
    load_s = time.perf_counter() - load_start

    for text, src, tgt in CASES:  # warm-up, not timed
        translator.translate(text, src, tgt)

    per_route: dict[str, list[float]] = {}
    for _ in range(REPEATS):
        for text, src, tgt in CASES:
            start = time.perf_counter()
            translator.translate(text, src, tgt)
            per_route.setdefault(f"{src}->{tgt}", []).append((time.perf_counter() - start) * 1000)

    every = [ms for times in per_route.values() for ms in times]
    print(
        json.dumps(
            {
                "device": "cpu",
                "machine": platform.machine(),
                "load_all_models_s": round(load_s, 1),
                "n": len(every),
                "p50_ms": round(statistics.median(every)),
                "p95_ms": round(percentile(every, 0.95)),
                "max_ms": round(max(every)),
                "per_route_median_ms": {
                    route: round(statistics.median(times)) for route, times in per_route.items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

"""Measure GPU memory with the three IndicTrans2 route models loaded at once (no Gnani calls).

Loads the routes one at a time, then translates one synthetic sentence per route so the peak
includes generation. Device-wide use (what the TTS/STT work and a browser compete for) comes from
`torch.cuda.mem_get_info`; run on AC power with other GPU-heavy apps closed.

    uv run --no-sync python scripts/measure_vram.py [route ...]

With no arguments all three routes are loaded; name routes to measure a subset.
"""

import sys

import torch

from saathi.translate import ROUTE_MODELS, RoutingTranslator

MIB = 1024 * 1024
# Synthetic, no personal data; one sentence per route. Kept short on purpose: the longest real
# turn is a 60 s clip, so the generation overhead printed here is a floor, not a ceiling.
SAMPLES: dict[str, tuple[str, str, str]] = {
    "indic-indic": ("मैं गेट नंबर 2 के पास हूँ, दूसरी मंज़िल पर आइए।", "hi", "kn"),
    "en-indic": ("I am near gate number 2, please come to the second floor.", "en", "hi"),
    "indic-en": ("ನಾನು ಗೇಟ್ ಸಂಖ್ಯೆ 2 ರ ಬಳಿ ಇದ್ದೇನೆ, ಎರಡನೇ ಮಹಡಿಗೆ ಬನ್ನಿ.", "kn", "en"),
}


def device_used_mib() -> float:
    free, total = torch.cuda.mem_get_info()
    return float((total - free) / MIB)  # float() keeps this typed when torch is absent (CI)


def report(label: str) -> None:
    print(
        f"{label:<28} allocated {torch.cuda.memory_allocated() / MIB:7.0f} MiB"
        f" | torch peak {torch.cuda.max_memory_allocated() / MIB:7.0f} MiB"
        f" | reserved {torch.cuda.memory_reserved() / MIB:7.0f} MiB"
        f" | device used {device_used_mib():7.0f} MiB"
    )


def main() -> int:
    if not torch.cuda.is_available():
        print("no CUDA device; nothing to measure", file=sys.stderr)
        return 1
    total = torch.cuda.get_device_properties(0).total_memory / MIB
    print(f"{torch.cuda.get_device_name(0)}, {total:.0f} MiB total")
    report("baseline (before any load)")

    routes = tuple(sys.argv[1:]) or tuple(ROUTE_MODELS)
    unknown = set(routes) - set(ROUTE_MODELS)
    if unknown:
        print(f"unknown routes: {sorted(unknown)}", file=sys.stderr)
        return 2

    router = RoutingTranslator()
    for route in routes:
        router.load((route,))
        report(f"after loading {route}")

    for route in routes:
        text, src, tgt = SAMPLES[route]
        result = router.translate_with_stats(text, src, tgt)
        report(f"after translating {route}")
        tokens = f"{result.longest_input_tokens} -> {result.longest_output_tokens}"
        print(f"    {route}: {tokens} tokens")
    print(f"free headroom of {total:.0f} MiB: {total - device_used_mib():.0f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

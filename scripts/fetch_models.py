"""Download the three IndicTrans2 models into the Hugging Face cache (HF_HOME).

Run by the container entrypoint before the server starts, so weights live in a mounted volume and
are never baked into the image. Safe to repeat: files already in the cache are not downloaded
again. Needs network only when something is missing. Spends no Gnani calls.
"""

import sys

from huggingface_hub import snapshot_download

from saathi.translate import MODEL_REVISIONS, ROUTE_MODELS


def main() -> int:
    for route, repo in ROUTE_MODELS.items():
        print(f"checking {route}: {repo}", flush=True)
        try:
            snapshot_download(repo_id=repo, revision=MODEL_REVISIONS[repo])
        except OSError as exc:
            print(f"could not fetch {repo}: {type(exc).__name__}", file=sys.stderr)
            return 1
    print("models ready", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Write a copy of the template with this machine's paths filled in.

Switch Console (0.40.1) doesn't fill `{params}` inside a managed agent's
`instructions`, so they reach the agent literally. This writes the values into
the document itself, and drops those params from the form.

Run: uv run python scripts/render_template.py --state-dir <absolute path>
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FILLED = ("team", "uv", "engine_dir", "state_dir")


def render(document: dict, values: dict[str, str]) -> dict:
    def fill(node):
        if isinstance(node, str):
            for name in FILLED:
                node = node.replace("{" + name + "}", values[name])
            return node
        if isinstance(node, list):
            return [fill(item) for item in node]
        if isinstance(node, dict):
            return {key: fill(value) for key, value in node.items()}
        return node

    params = {name: spec for name, spec in document["params"].items() if name not in FILLED}
    body = {key: value for key, value in document.items() if key != "params"}
    return {"version": document["version"], "params": params, **{k: v for k, v in fill(body).items() if k != "version"}}


def posix(path: str) -> str:
    return path.replace("\\", "/")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--engine-dir", default=str(ROOT))
    parser.add_argument("--uv", default=shutil.which("uv"))
    parser.add_argument("--team", default="precedent")
    parser.add_argument("--out", type=Path, default=ROOT / "precedent.local.template.yaml")
    args = parser.parse_args()
    if not args.uv:
        parser.error("uv isn't on PATH; pass --uv with its full path")
    document = yaml.safe_load((ROOT / "precedent.template.yaml").read_text(encoding="utf-8"))
    rendered = render(
        document,
        {"team": args.team, "uv": posix(args.uv), "engine_dir": posix(args.engine_dir), "state_dir": posix(args.state_dir)},
    )
    args.out.write_text(yaml.safe_dump(rendered, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

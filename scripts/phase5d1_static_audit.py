"""Static Phase 5D1 audit for the browser-facing frontend surface.

The audit deliberately scans only runtime/browser source plus the built static
bundle. Test/docs files may name forbidden tokens in assertions and runbooks,
so they are not treated as shipped browser code.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


ALLOWED_PUBLIC_ENV = {
    "NEXT_PUBLIC_API_BASE_URL",
    "NEXT_PUBLIC_DEMO_TENANT_ID",
}

FORBIDDEN_BROWSER_TOKENS = (
    "DATABASE_URL",
    "GOOGLE_API_KEY",
    "NORTHFLANK_ADMIN",
    "NORTHFLANK_ADMIN_URI",
    "POSTGRES_PASSWORD",
    "DB_PASSWORD",
    "PHASE6D_ACCEPTANCE_TOKEN",
    "X-Acceptance-Token",
    "postgresql://",
    "postgres://",
    "chain_of_thought",
    "model_reasoning",
)

TEXT_SUFFIXES = {
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".json",
    ".html",
    ".css",
    ".map",
}


def _text_files(root: Path):
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def runtime_source_files(frontend_root: Path) -> list[Path]:
    paths: list[Path] = []
    for relative in ("app", "components", "lib"):
        paths.extend(_text_files(frontend_root / relative) or ())
    for relative in ("next.config.ts", ".env.example"):
        candidate = frontend_root / relative
        if candidate.is_file():
            paths.append(candidate)
    return sorted(set(paths))


def public_env_names(paths: list[Path]) -> set[str]:
    pattern = re.compile(r"NEXT_PUBLIC_[A-Z0-9_]+")
    names: set[str] = set()
    for path in paths:
        names.update(pattern.findall(_read(path)))
    return names


def forbidden_hits(paths: list[Path]) -> list[str]:
    hits: list[str] = []
    for path in paths:
        content = _read(path)
        lowered = content.lower()
        for token in FORBIDDEN_BROWSER_TOKENS:
            if token.lower() in lowered:
                hits.append(f"{path}: forbidden token {token}")
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frontend-root",
        default="frontend",
        help="Frontend package root.",
    )
    parser.add_argument(
        "--bundle-root",
        default=None,
        help="Optional built static bundle directory, e.g. frontend/.next/static.",
    )
    args = parser.parse_args()

    frontend_root = Path(args.frontend_root).resolve()
    source_paths = runtime_source_files(frontend_root)

    names = public_env_names(source_paths)
    if names != ALLOWED_PUBLIC_ENV:
        print(
            "Unexpected NEXT_PUBLIC env contract: "
            f"expected {sorted(ALLOWED_PUBLIC_ENV)}, got {sorted(names)}",
            file=sys.stderr,
        )
        return 1

    hits = forbidden_hits(source_paths)
    if hits:
        print("\n".join(hits), file=sys.stderr)
        return 1

    if args.bundle_root is not None:
        bundle_root = Path(args.bundle_root).resolve()
        if not bundle_root.exists():
            print(
                f"Built bundle directory does not exist: {bundle_root}",
                file=sys.stderr,
            )
            return 1
        bundle_paths = list(_text_files(bundle_root) or ())
        bundle_hits = forbidden_hits(bundle_paths)
        if bundle_hits:
            print("\n".join(bundle_hits), file=sys.stderr)
            return 1

    print(
        "PASS: public env contract is exact and no forbidden browser tokens "
        "were found."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

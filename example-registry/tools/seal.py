#!/usr/bin/env python3
"""seal.py - write manifest.sha256 for a registry root.

    python3 seal.py [--root REGISTRY_ROOT]

Hashes registry.json and every file under prompts/ (if present) and writes
"<sha256>  <relative path>" lines, sorted. Run it after any intended registry
change; until you do, the resolver treats the change as tampering.
"""
import argparse
import hashlib
import os


def main():
    ap = argparse.ArgumentParser(description="Seal an instruction registry root.")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    root = ap.parse_args().root
    files = ["registry.json"]
    prompts = os.path.join(root, "prompts")
    if os.path.isdir(prompts):
        for dirpath, _, names in os.walk(prompts):
            for n in names:
                files.append(os.path.relpath(os.path.join(dirpath, n), root))
    lines = []
    for rel in sorted(files):
        with open(os.path.join(root, rel), "rb") as f:
            lines.append(f"{hashlib.sha256(f.read()).hexdigest()}  {rel}")
    with open(os.path.join(root, "manifest.sha256"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"sealed {len(lines)} file(s)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""resolve.py - reference resolver for the Instruction gate.

    python3 resolve.py NAME@N --root REGISTRY_ROOT

Resolves one version-pinned instruction reference against a registry, after
verifying that every file listed in REGISTRY_ROOT/manifest.sha256 still has the
hash recorded there (and that registry.json is one of them).

Contract used by gate.mjs:
  exit 0, prints "RESOLVED NAME@N: <summary>"   the reference is valid
  exit 1, prints "REJECTED: <reason>"           unknown, malformed, revoked, or
                                                the manifest does not verify

A superseded version still resolves: pinning an older version on purpose is
allowed. Only a version marked "revoked": true is refused.

Registry shape (registry.json):
  {"registry_version": 1, "prompts": {"NAME": {"current": 2,
     "versions": {"1": {"summary": "...", "status": "superseded"},
                  "2": {"summary": "...", "status": "active"}}}}}

Standard library only. Writes nothing.
"""
import argparse
import hashlib
import json
import os
import re
import sys

PINNED = re.compile(r"^([A-Z][A-Z0-9_]*(?:\.[A-Z0-9_]+)+)@([1-9][0-9]*)$")


class Rejected(Exception):
    pass


def verify_manifest(root):
    path = os.path.join(root, "manifest.sha256")
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError as e:
        raise Rejected(f"manifest unreadable: {e.strerror}")
    listed = set()
    for n, line in enumerate(lines, 1):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise Rejected(f"manifest line {n} is malformed")
        digest, rel = parts[0], parts[1].strip()
        if os.path.isabs(rel) or ".." in rel.split("/"):
            raise Rejected(f"manifest line {n} names a path outside the root")
        full = os.path.join(root, rel)
        if os.path.islink(full):
            raise Rejected(f"{rel} is a symlink")
        try:
            data = open(full, "rb").read()
        except OSError:
            raise Rejected(f"{rel} is listed in the manifest but missing")
        if hashlib.sha256(data).hexdigest() != digest:
            raise Rejected(f"{rel} does not match its manifest hash (tampered or not resealed)")
        listed.add(rel)
    if "registry.json" not in listed:
        raise Rejected("registry.json is not covered by the manifest")


def resolve(ref, root):
    m = PINNED.fullmatch(ref)
    if not m:
        raise Rejected(f"'{ref}' is not a version-pinned reference (expected NAME@N)")
    name, version = m.group(1), m.group(2)
    verify_manifest(root)
    try:
        registry = json.load(open(os.path.join(root, "registry.json"), encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Rejected(f"registry unreadable: {e}")
    entry = (registry.get("prompts") or {}).get(name)
    if not isinstance(entry, dict):
        raise Rejected(f"{name} is not registered")
    ver = (entry.get("versions") or {}).get(version)
    if not isinstance(ver, dict):
        raise Rejected(f"{name} has no version {version}")
    if ver.get("revoked") is True:
        raise Rejected(f"{name}@{version} is revoked")
    return f"RESOLVED {name}@{version}: {ver.get('summary', '')}".rstrip(": ")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Resolve a pinned instruction reference.")
    ap.add_argument("ref", help="pinned reference, e.g. AGENT.ESCALATION@1")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    args = ap.parse_args(argv)
    try:
        print(resolve(args.ref, args.root))
        return 0
    except Rejected as e:
        print(f"REJECTED: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

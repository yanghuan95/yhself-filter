#!/usr/bin/env python3
"""Generate portable domain rule sets from the two maintained source lists."""

import argparse
import ipaddress
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


SOURCES = ("selfdirect", "special")
ALIASES = {
    "HOST": "DOMAIN",
    "HOST-SUFFIX": "DOMAIN-SUFFIX",
    "HOST-KEYWORD": "DOMAIN-KEYWORD",
    "DOMAIN": "DOMAIN",
    "DOMAIN-SUFFIX": "DOMAIN-SUFFIX",
    "DOMAIN-KEYWORD": "DOMAIN-KEYWORD",
}
QX_TYPES = {
    "DOMAIN": "host",
    "DOMAIN-SUFFIX": "host-suffix",
    "DOMAIN-KEYWORD": "host-keyword",
}
SING_BOX_FIELDS = {
    "DOMAIN": "domain",
    "DOMAIN-SUFFIX": "domain_suffix",
    "DOMAIN-KEYWORD": "domain_keyword",
}


def parse_rules(path):
    rules = []
    seen = set()
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", "//", ";")):
            continue
        parts = [part.strip() for part in line.split(",")]

        def fail(message):
            raise ValueError(f"{path.name}:{number}: {message}: {line}")

        if len(parts) not in (2, 3):
            fail("expected TYPE,value[,DIRECT]")
        kind = ALIASES.get(parts[0].upper())
        if kind is None:
            fail("unsupported rule type (only DOMAIN/HOST, suffix and keyword are portable here)")
        if len(parts) == 3 and parts[2].upper() != "DIRECT":
            fail("only DIRECT is supported; other policies cannot be preserved in a headless rule set")
        value = parts[1].lower()
        if kind == "DOMAIN-KEYWORD":
            if not re.fullmatch(r"[a-z0-9_.-]+", value):
                fail("invalid domain keyword")
        else:
            try:
                value = value.encode("idna").decode("ascii")
            except UnicodeError:
                fail("invalid domain")
            labels = value.split(".")
            if len(value) > 253 or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in labels
            ):
                fail("expected a domain without wildcard, URL, port or leading/trailing dot")
            try:
                ipaddress.ip_address(value)
            except ValueError:
                pass
            else:
                fail("an IP address is not a domain rule")
        rule = (kind, value)
        if rule not in seen:
            seen.add(rule)
            rules.append(rule)
    return rules


def render_rules(rules):
    classical = [f"{kind},{value}" for kind, value in rules]
    headless = {}
    for kind, field in SING_BOX_FIELDS.items():
        values = [value for rule_kind, value in rules if rule_kind == kind]
        if values:
            headless[field] = values
    mihomo = "payload:\n" + "".join(f"  - {json.dumps(line)}\n" for line in classical)
    return {
        "quantumult-x": "".join(f"{QX_TYPES[kind]},{value},direct\n" for kind, value in rules),
        "loon": "".join(f"{line}\n" for line in classical),
        "shadowrocket": "".join(f"{line}\n" for line in classical),
        "mihomo": mihomo if classical else "payload: []\n",
        "sing-box": json.dumps({"version": 2, "rules": [headless] if headless else []}, indent=2) + "\n",
        "legacy-clash": "".join(f"{line},DIRECT\n" for line in classical),
    }


def build(root, sing_box="sing-box"):
    # Validate both sources and compile everything before replacing published files.
    parsed = {name: parse_rules(root / f"{name}.list") for name in SOURCES}
    with tempfile.TemporaryDirectory(prefix="yhself-rules-") as temp:
        staging = Path(temp)
        for name, rules in parsed.items():
            rendered = render_rules(rules)
            for platform in ("quantumult-x", "loon", "shadowrocket", "mihomo", "sing-box"):
                extension = {"mihomo": "yaml", "sing-box": "json"}.get(platform, "list")
                path = staging / "rules" / platform / f"{name}.{extension}"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(rendered[platform], encoding="utf-8")
            source = staging / "rules" / "sing-box" / f"{name}.json"
            subprocess.run([sing_box, "rule-set", "compile", str(source), "-o", str(source.with_suffix(".srs"))], check=True)
            if name == "selfdirect":
                shutil.copyfile(source, staging / "selfdirect.json")
                shutil.copyfile(source.with_suffix(".srs"), staging / "selfdirect.srs")
                (staging / "selfClashDirect.list").write_text(rendered["legacy-clash"], encoding="utf-8")
        for source in sorted(staging.rglob("*")):
            if source.is_file():
                destination = root / source.relative_to(staging)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
    for name, rules in parsed.items():
        print(f"{name}: {len(rules)} unique rules -> 5 platforms")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--sing-box", default="sing-box", help="path to the sing-box compiler")
    args = parser.parse_args()
    try:
        build(args.root, args.sing_box)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

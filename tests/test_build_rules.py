import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.build_rules import build, parse_rules, render_rules


class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def parse(self, text):
        path = self.root / "special.list"
        path.write_text(text, encoding="utf-8")
        return parse_rules(path)

    def test_aliases_comments_bom_and_deduplication(self):
        rules = self.parse(
            "\ufeff# comment\r\n; comment\n// comment\n\n"
            " host, Exact.Example, direct \nDOMAIN,exact.example,DIRECT\n"
            "HOST-SUFFIX,suffix.example\nDOMAIN-SUFFIX,suffix.example,direct\n"
            "HOST-KEYWORD,Keyword,DIRECT\nDOMAIN-KEYWORD,keyword\n"
        )
        self.assertEqual(rules, [
            ("DOMAIN", "exact.example"),
            ("DOMAIN-SUFFIX", "suffix.example"),
            ("DOMAIN-KEYWORD", "keyword"),
        ])

    def test_every_rule_is_preserved_in_each_platform(self):
        rules = self.parse("HOST,exact.example,direct\nDOMAIN-SUFFIX,suffix.example\nHOST-KEYWORD,keyword\n")
        rendered = render_rules(rules)
        classical = "DOMAIN,exact.example\nDOMAIN-SUFFIX,suffix.example\nDOMAIN-KEYWORD,keyword\n"
        self.assertEqual(rendered["quantumult-x"], "host,exact.example,direct\nhost-suffix,suffix.example,direct\nhost-keyword,keyword,direct\n")
        self.assertEqual(rendered["loon"], classical)
        self.assertEqual(rendered["shadowrocket"], classical)
        self.assertEqual(rendered["mihomo"], 'payload:\n  - "DOMAIN,exact.example"\n  - "DOMAIN-SUFFIX,suffix.example"\n  - "DOMAIN-KEYWORD,keyword"\n')
        self.assertEqual(json.loads(rendered["sing-box"]), {
            "version": 2,
            "rules": [{"domain": ["exact.example"], "domain_suffix": ["suffix.example"], "domain_keyword": ["keyword"]}],
        })
        self.assertEqual(rendered["legacy-clash"], "DOMAIN,exact.example,DIRECT\nDOMAIN-SUFFIX,suffix.example,DIRECT\nDOMAIN-KEYWORD,keyword,DIRECT\n")

    def test_empty_list_does_not_become_a_match_all_rule(self):
        rendered = render_rules(self.parse("# no rules\n"))
        self.assertEqual(json.loads(rendered["sing-box"])["rules"], [])
        self.assertEqual(rendered["mihomo"], "payload: []\n")
        self.assertEqual(rendered["quantumult-x"], "")

    def test_rejects_invalid_input_with_source_location(self):
        invalid = [
            "DOMAIN", "DOMAIN,", "DOMAIN,example.com,DIRECT,extra",
            "GEOIP,CN,DIRECT", "IP-CIDR,10.0.0.0/8,DIRECT", "DOMAIN,example.com,PROXY",
            "DOMAIN,example.com,", "DOMAIN,*.example.com,DIRECT",
            "DOMAIN,https://example.com,DIRECT", "DOMAIN,example.com:443,DIRECT",
            "DOMAIN,.example.com,DIRECT", "DOMAIN,example.com.,DIRECT",
            "DOMAIN,192.168.1.1,DIRECT", "DOMAIN,-bad.example,DIRECT",
            "DOMAIN,example..com,DIRECT", "DOMAIN-KEYWORD,,DIRECT",
            "DOMAIN-KEYWORD,hello world,DIRECT", "DOMAIN,example.com,DIRECT # comment",
        ]
        for line in invalid:
            with self.subTest(line=line), self.assertRaisesRegex(ValueError, r"special.list:2:"):
                self.parse("# heading\n" + line)

    def test_invalid_second_source_leaves_all_published_files_untouched(self):
        (self.root / "selfdirect.list").write_text("HOST,valid.example,direct\n")
        (self.root / "special.list").write_text("GEOIP,CN,DIRECT\n")
        (self.root / "selfdirect.json").write_text("previous output")
        with patch("scripts.build_rules.subprocess.run") as compiler:
            with self.assertRaises(ValueError):
                build(self.root)
        compiler.assert_not_called()
        self.assertEqual((self.root / "selfdirect.json").read_text(), "previous output")
        self.assertFalse((self.root / "rules").exists())

    def test_compiler_failure_leaves_all_published_files_untouched(self):
        for name in ("selfdirect", "special"):
            (self.root / f"{name}.list").write_text("DOMAIN,valid.example,DIRECT\n")
        (self.root / "selfdirect.json").write_text("previous output")
        with patch("scripts.build_rules.subprocess.run", side_effect=subprocess.CalledProcessError(1, "sing-box")):
            with self.assertRaises(subprocess.CalledProcessError):
                build(self.root)
        self.assertEqual((self.root / "selfdirect.json").read_text(), "previous output")
        self.assertFalse((self.root / "rules").exists())

    def test_second_compile_failure_does_not_publish_the_first_source(self):
        for name in ("selfdirect", "special"):
            (self.root / f"{name}.list").write_text("DOMAIN,valid.example,DIRECT\n")
        (self.root / "selfdirect.json").write_text("previous output")

        def compile_first_only(command, **kwargs):
            if "special.json" in command[3]:
                raise subprocess.CalledProcessError(1, command)
            Path(command[-1]).write_bytes(b"compiled")

        with patch("scripts.build_rules.subprocess.run", side_effect=compile_first_only):
            with self.assertRaises(subprocess.CalledProcessError):
                build(self.root)
        self.assertEqual((self.root / "selfdirect.json").read_text(), "previous output")
        self.assertFalse((self.root / "rules").exists())


SING_BOX = os.environ.get("SING_BOX_BIN") or shutil.which("sing-box")


@unittest.skipUnless(SING_BOX, "sing-box compiler is not installed")
class CompilerTests(unittest.TestCase):
    def test_both_sources_compile_independently_and_rebuild_identically(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "selfdirect.list").write_text("HOST,exact.example,direct\nHOST-SUFFIX,suffix.example,direct\nHOST-KEYWORD,keyword,direct\n")
            (root / "special.list").write_text("DOMAIN-SUFFIX,special.example,DIRECT\n")
            build(root, SING_BOX)
            paths = sorted((root / "rules").rglob("*"))
            first = {str(path.relative_to(root)): path.read_bytes() for path in paths if path.is_file()}
            self.assertEqual(len(first), 12)
            self.assertEqual((root / "rules/loon/special.list").read_text(), "DOMAIN-SUFFIX,special.example\n")
            self.assertEqual((root / "selfdirect.json").read_bytes(), (root / "rules/sing-box/selfdirect.json").read_bytes())
            self.assertEqual((root / "selfdirect.srs").read_bytes(), (root / "rules/sing-box/selfdirect.srs").read_bytes())
            for name, domain, matches in [
                ("selfdirect", "exact.example", True),
                ("selfdirect", "sub.exact.example", False),
                ("selfdirect", "suffix.example", True),
                ("selfdirect", "sub.suffix.example", True),
                ("selfdirect", "has-keyword.example", True),
                ("selfdirect", "special.example", False),
                ("special", "sub.special.example", True),
                ("special", "exact.example", False),
            ]:
                with self.subTest(name=name, domain=domain):
                    result = subprocess.run([SING_BOX, "rule-set", "match", "-f", "binary", str(root / f"rules/sing-box/{name}.srs"), domain], check=True, capture_output=True, text=True)
                    self.assertEqual("match rules." in result.stdout + result.stderr, matches)
            for name in ("selfdirect", "special"):
                output = root / f"{name}-decompiled.json"
                subprocess.run([SING_BOX, "rule-set", "decompile", str(root / f"rules/sing-box/{name}.srs"), "-o", str(output)], check=True)
                decoded = json.loads(output.read_text())
                expected = json.loads((root / f"rules/sing-box/{name}.json").read_text())
                # The compiler emits scalar values for single-element arrays.
                normalized = [{key: value if isinstance(value, list) else [value] for key, value in rule.items()} for rule in decoded["rules"]]
                self.assertEqual(normalized, expected["rules"])
            build(root, SING_BOX)
            self.assertEqual(first, {key: (root / key).read_bytes() for key in first})

    def test_empty_source_compiles_without_matching_unrelated_domains(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("selfdirect", "special"):
                (root / f"{name}.list").write_text("# intentionally empty\n")
            build(root, SING_BOX)
            for name in ("selfdirect", "special"):
                result = subprocess.run([SING_BOX, "rule-set", "match", "-f", "binary", str(root / f"rules/sing-box/{name}.srs"), "unrelated.example"], check=True, capture_output=True, text=True)
                self.assertNotIn("match rules.", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

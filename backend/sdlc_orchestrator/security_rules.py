"""Deterministic security rules run on added lines before the LLM review.

The rules give the security agent concrete, line-anchored evidence to reason
about, and they keep working when no model is available.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .diff import FileChange


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    severity: str  # critical | high | medium | low
    cwe: str
    pattern: re.Pattern[str]
    languages: frozenset[str] | None = None  # None means any language
    fix: str = ""


def _r(id, title, severity, cwe, pattern, languages=None, fix=""):
    return Rule(id, title, severity, cwe, re.compile(pattern), frozenset(languages) if languages else None, fix)


RULES: list[Rule] = [
    _r("SEC001", "AWS access key ID committed", "critical", "CWE-798", r"\b(AKIA|ASIA)[0-9A-Z]{16}\b",
       fix="Remove the key, rotate it in IAM, and load credentials from the environment or a secrets manager."),
    _r("SEC002", "Private key committed", "critical", "CWE-321", r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
       fix="Remove the key from the repository and rotate it."),
    _r("SEC003", "Hardcoded password or secret", "high", "CWE-798",
       r"""(?i)\b\w*(password|passwd|secret|api_?key|access_?key|token)\w*\b['"]?\s*[:=]\s*['"][^'"\s]{6,}['"]""",
       fix="Read the value from configuration or a secrets manager instead of source code."),
    _r("SEC004", "Shell command built with shell=True", "high", "CWE-78", r"subprocess\.\w+\(.*shell\s*=\s*True",
       {"python"}, fix="Pass an argument list and leave shell=False."),
    _r("SEC005", "os.system call", "medium", "CWE-78", r"\bos\.system\(", {"python"},
       fix="Use subprocess.run with an argument list."),
    _r("SEC006", "Dynamic code execution", "high", "CWE-95", r"(?<![\w.])(eval|exec)\(", {"python", "javascript", "typescript"},
       fix="Avoid evaluating strings as code; parse the input explicitly."),
    _r("SEC007", "SQL built with string formatting", "high", "CWE-89",
       r"""(?i)(execute|query)\(\s*(f['"]|['"].*['"]\s*(%|\+|\.format))""",
       fix="Use parameterized queries."),
    _r("SEC008", "Unsafe deserialization", "high", "CWE-502", r"\b(pickle\.loads?|yaml\.load)\((?!.*SafeLoader)", {"python"},
       fix="Use yaml.safe_load, or avoid unpickling untrusted data."),
    _r("SEC009", "TLS verification disabled", "medium", "CWE-295", r"verify\s*=\s*False|rejectUnauthorized:\s*false|_create_unverified_context\(|CERT_NONE",
       fix="Keep certificate verification on; trust a custom CA bundle if needed."),
    _r("SEC010", "Weak hash for security use", "low", "CWE-328", r"\bhashlib\.(md5|sha1)\(|createHash\(['\"](md5|sha1)",
       fix="Use SHA-256 or a password hashing function such as bcrypt or argon2."),
    _r("SEC011", "Raw HTML injection", "medium", "CWE-79", r"dangerouslySetInnerHTML|\.innerHTML\s*=",
       {"javascript", "typescript"}, fix="Render text, or sanitize the HTML with DOMPurify first."),
    _r("SEC012", "Debug mode enabled", "low", "CWE-489", r"(?i)\bdebug\s*=\s*True\b", {"python"},
       fix="Drive debug mode from configuration and keep it off in production."),
]


@dataclass
class Finding:
    id: str
    rule: str
    title: str
    severity: str
    cwe: str
    file: str
    line: int
    snippet: str
    fix: str
    source: str = "rule"  # rule | llm
    explanation: str = ""
    dismissed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def scan(files: list[FileChange]) -> list[Finding]:
    findings: list[Finding] = []
    for f in files:
        if f.status == "deleted":
            continue
        for added in f.added_lines:
            stripped = added.text.strip()
            if stripped.startswith(("#", "//")):
                continue
            for rule in RULES:
                if rule.languages and f.language not in rule.languages:
                    continue
                if rule.pattern.search(added.text):
                    findings.append(
                        Finding(
                            id=f"{rule.id}-{f.path}:{added.line}",
                            rule=rule.id,
                            title=rule.title,
                            severity=rule.severity,
                            cwe=rule.cwe,
                            file=f.path,
                            line=added.line,
                            snippet=stripped[:200],
                            fix=rule.fix,
                        )
                    )
    findings.sort(key=lambda x: (SEVERITY_ORDER[x.severity], x.file, x.line))
    return findings

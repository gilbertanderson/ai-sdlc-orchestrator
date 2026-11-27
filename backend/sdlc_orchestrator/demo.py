"""Sample repositories with realistic feature branches to try the pipeline on.

Each scenario is a small invoicing repo with the same `main` branch and a different
feature branch:

- ``invoicing``: percentage and bulk discounts with a real off-by-one bug
  (``bulk_tier(50)`` returns 5 instead of the documented 10), plus an export module
  with a hardcoded API key, ``shell=True``, string-built SQL and disabled TLS checks.
- ``clean``: line totals with tax, documented, correct, and tested by the author.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

BASE_FILES = {
    "README.md": "# invoices\n\nTiny invoicing helpers.\n",
    "invoices/__init__.py": "",
    "invoices/pricing.py": '''"""Price calculations."""


def subtotal(items):
    """Sum quantity * unit price.

    >>> subtotal([(2, 5.0), (1, 2.5)])
    12.5
    """
    return sum(qty * price for qty, price in items)
''',
}

DISCOUNTS_PRICING = '''"""Price calculations."""


def subtotal(items):
    """Sum quantity * unit price.

    >>> subtotal([(2, 5.0), (1, 2.5)])
    12.5
    """
    return sum(qty * price for qty, price in items)


def apply_discount(amount, percent):
    """Reduce an amount by a percentage between 0 and 100.

    >>> apply_discount(200, 10)
    180.0
    >>> apply_discount(50, 0)
    50.0
    >>> apply_discount(100, 150)
    Traceback (most recent call last):
    ValueError: percent must be between 0 and 100
    """
    if percent < 0 or percent > 100:
        raise ValueError("percent must be between 0 and 100")
    return round(amount * (1 - percent / 100), 2)


def bulk_tier(quantity):
    """Discount percent for bulk orders: 5% from 10 units, 10% from 50 units.

    >>> bulk_tier(9)
    0
    >>> bulk_tier(10)
    5
    >>> bulk_tier(50)
    10
    """
    if quantity > 50:
        return 10
    if quantity >= 10:
        return 5
    return 0
'''

EXPORT = '''"""Exporting invoices to the accounting system."""

import ssl
import subprocess
import urllib.request

ACCOUNTING_API_KEY = "sk_live_51Hq8x2Yb7cK9pLmN0"


def upload(invoice_path, customer):
    subprocess.run(f"gzip -k {invoice_path}", shell=True, check=True)
    with open(invoice_path + ".gz", "rb") as fh:
        req = urllib.request.Request(
            f"https://accounting.example.com/api/invoices?customer={customer}",
            data=fh.read(),
            headers={"Authorization": f"Bearer {ACCOUNTING_API_KEY}"},
        )
    return urllib.request.urlopen(req, context=ssl._create_unverified_context())


def find_customer(db, name):
    return db.execute(f"SELECT * FROM customers WHERE name = '{name}'").fetchone()
'''

LINE_TOTALS_PRICING = '''"""Price calculations."""


def line_total(quantity, unit_price, tax_percent=0):
    """Price of one invoice line with optional tax, rounded to cents.

    >>> line_total(2, 5.0)
    10.0
    >>> line_total(3, 2.5, tax_percent=8)
    8.1
    >>> line_total(-1, 5.0)
    Traceback (most recent call last):
    ValueError: quantity must not be negative
    """
    if quantity < 0:
        raise ValueError("quantity must not be negative")
    return round(quantity * unit_price * (1 + tax_percent / 100), 2)


def subtotal(items, tax_percent=0):
    """Sum of every line on the invoice, with optional tax.

    >>> subtotal([(2, 5.0), (1, 2.5)])
    12.5
    >>> subtotal([(2, 5.0)], tax_percent=10)
    11.0
    """
    return round(sum(line_total(qty, price, tax_percent) for qty, price in items), 2)
'''

LINE_TOTALS_TESTS = '''import pytest

from invoices.pricing import line_total, subtotal


def test_line_total_adds_tax():
    assert line_total(4, 2.5, tax_percent=10) == 11.0


def test_line_total_rejects_negative_quantity():
    with pytest.raises(ValueError):
        line_total(-2, 1.0)


def test_subtotal_of_an_empty_invoice_is_zero():
    assert subtotal([]) == 0
'''

LINE_TOTALS_README = """# invoices

Tiny invoicing helpers.

- `line_total(quantity, unit_price, tax_percent=0)` prices one line, rounded to cents.
- `subtotal(items, tax_percent=0)` adds up the lines on an invoice.
"""


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    blurb: str
    head: str
    commits: tuple[tuple[str, dict[str, str]], ...]
    base: str = "main"


SCENARIOS: dict[str, Scenario] = {
    "invoicing": Scenario(
        id="invoicing",
        title="A discount bug and leaked secrets",
        blurb="An off-by-one in bulk discounts and four security issues in a new export module.",
        head="feature/discounts",
        commits=(
            ("Add percentage and bulk discounts", {"invoices/pricing.py": DISCOUNTS_PRICING}),
            ("Upload invoices to the accounting system", {"invoices/export.py": EXPORT}),
        ),
    ),
    "clean": Scenario(
        id="clean",
        title="A clean change",
        blurb="Line totals with tax, documented and tested by the author: what a passing run looks like.",
        head="feature/line-totals",
        commits=(
            ("Add line totals with tax", {"invoices/pricing.py": LINE_TOTALS_PRICING}),
            ("Test line totals and subtotals", {"tests/test_pricing.py": LINE_TOTALS_TESTS}),
            ("Document line totals", {"README.md": LINE_TOTALS_README}),
        ),
    ),
}

# Kept for callers that only know the original demo.
FEATURE_FILES = {"invoices/pricing.py": DISCOUNTS_PRICING, "invoices/export.py": EXPORT}


def get_scenario(scenario: str) -> Scenario:
    try:
        return SCENARIOS[scenario]
    except KeyError:
        raise ValueError(f"Unknown demo scenario {scenario!r}; choose from {', '.join(SCENARIOS)}") from None


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Demo", "-c", "user.email=demo@example.com", *args],
        check=True,
        capture_output=True,
    )


def _write(repo: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def make_demo_repo(path: str | Path | None = None, scenario: str = "invoicing") -> Path:
    """Create a repo with `main` and the scenario's feature branch. Returns its path."""
    spec = get_scenario(scenario)
    repo = Path(path) if path else Path(tempfile.mkdtemp(prefix="sdlc-demo-"))
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", spec.base, str(repo)], check=True)
    _write(repo, BASE_FILES)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "Initial invoicing helpers")
    _git(repo, "checkout", "-q", "-b", spec.head)
    for message, files in spec.commits:
        _write(repo, files)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", message)
    return repo

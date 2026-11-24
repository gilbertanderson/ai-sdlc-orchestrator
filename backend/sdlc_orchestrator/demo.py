"""Builds a small sample repository with a realistic feature branch to try the pipeline on."""

from __future__ import annotations

import subprocess
import tempfile
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

FEATURE_FILES = {
    "invoices/pricing.py": '''"""Price calculations."""


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
''',
    "invoices/export.py": '''"""Exporting invoices to the accounting system."""

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
''',
}


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
        p.write_text(text)


def make_demo_repo(path: str | Path | None = None) -> Path:
    """Create a repo with `main` and a `feature/discounts` branch. Returns its path."""
    repo = Path(path) if path else Path(tempfile.mkdtemp(prefix="sdlc-demo-"))
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _write(repo, BASE_FILES)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "Initial invoicing helpers")
    _git(repo, "checkout", "-q", "-b", "feature/discounts")
    _write(repo, {"invoices/pricing.py": FEATURE_FILES["invoices/pricing.py"]})
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "Add percentage and bulk discounts")
    _write(repo, {"invoices/export.py": FEATURE_FILES["invoices/export.py"]})
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "Upload invoices to the accounting system")
    return repo

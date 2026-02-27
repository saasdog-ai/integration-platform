#!/usr/bin/env python3
"""Generate test data in the internal database for sync testing.

Seeds sample_vendors, sample_bills, and sample_invoices with realistic
test data. Records are created with external_id = NULL so they appear
as "not yet synced" for outbound sync testing.

Usage:
    python scripts/generate_test_data.py
    python scripts/generate_test_data.py --vendors 20 --bills 40 --invoices 30
    python scripts/generate_test_data.py --client-id aaa00000-0000-0000-0000-000000000001
    python scripts/generate_test_data.py --dry-run --vendors 5
    python scripts/generate_test_data.py --clear  # Remove all test data first
"""

import argparse
import asyncio
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

DEFAULT_CLIENT_ID = "aaa00000-0000-0000-0000-000000000001"
DEFAULT_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5433/job_runner"

# ---------------------------------------------------------------------------
# Realistic test data pools
# ---------------------------------------------------------------------------

COMPANY_NAMES = [
    "Acme Manufacturing Co.",
    "Pacific Coast Supplies",
    "Summit Technology Partners",
    "Greenfield Consulting Group",
    "Atlas Industrial Services",
    "Horizon Digital Solutions",
    "Pinnacle Office Supplies",
    "Cascade Building Materials",
    "Metro Freight Services",
    "Silverline Cleaning Solutions",
    "BlueStar IT Consulting",
    "Continental Food Distributors",
    "Northwind Equipment Rental",
    "Redwood Financial Advisors",
    "CloudBridge Software Inc.",
    "Omega Security Systems",
    "Velocity Courier Services",
    "Ironclad Construction LLC",
    "Sapphire HR Solutions",
    "Keystone Marketing Agency",
    "Prairie Farms Cooperative",
    "Beacon Health Services",
    "TrueNorth Legal Consulting",
    "Granite State Landscaping",
    "Maverick Auto Parts",
    "Windward Shipping Co.",
    "Emerald City Catering",
    "Apex Engineering Group",
    "Sunflower Energy Corp.",
    "Diamond Edge Printing",
]

BILL_DESCRIPTIONS = [
    "Office supplies and stationery",
    "Monthly IT support contract",
    "Building maintenance services",
    "Professional consulting fees",
    "Shipping and logistics",
    "Equipment rental — Q1",
    "Marketing campaign materials",
    "Software license renewal",
    "Cleaning services — monthly",
    "Travel and accommodation expenses",
    "Insurance premium payment",
    "Legal services retainer",
    "Warehouse storage fees",
    "Telecommunications services",
    "Training and development",
    "Raw materials purchase order",
    "Fleet vehicle maintenance",
    "Printing and reproduction",
    "Catering for corporate event",
    "Security monitoring services",
]

INVOICE_MEMOS = [
    "Professional services rendered",
    "Project milestone delivery",
    "Monthly retainer — consulting",
    "Software development sprint",
    "Design and branding package",
    "Annual maintenance contract",
    "Marketing strategy deliverables",
    "Financial audit services",
    "Technical support hours",
    "Website development phase",
]

LINE_ITEM_DESCRIPTIONS = [
    "Consulting hours",
    "Development services",
    "Design work",
    "Project management",
    "Quality assurance",
    "Administrative support",
    "Travel expenses",
    "Materials and supplies",
    "Software licenses",
    "Training sessions",
    "Equipment rental",
    "Maintenance services",
    "Research and analysis",
    "Content creation",
    "Data entry services",
]

US_STATES = ["CA", "NY", "TX", "FL", "IL", "WA", "CO", "MA", "GA", "VA"]
US_CITIES = [
    "San Francisco", "New York", "Austin", "Miami", "Chicago",
    "Seattle", "Denver", "Boston", "Atlanta", "Richmond",
]


def _random_phone() -> str:
    return f"({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"


def _random_email(company: str) -> str:
    domain = company.lower().split()[0].replace(",", "").replace(".", "")
    prefix = random.choice(["accounts", "billing", "ap", "finance", "info"])
    return f"{prefix}@{domain}.com"


def _random_address() -> dict:
    idx = random.randint(0, len(US_STATES) - 1)
    return {
        "street_1": f"{random.randint(100, 9999)} {random.choice(['Main', 'Oak', 'Elm', 'Park', 'Industrial'])} {random.choice(['St', 'Ave', 'Blvd', 'Dr'])}",
        "street_2": random.choice([None, f"Suite {random.randint(100, 999)}", f"Unit {random.randint(1, 50)}"]),
        "city": US_CITIES[idx],
        "state": US_STATES[idx],
        "zip_code": f"{random.randint(10000, 99999)}",
        "country": "US",
    }


def _random_line_items(count: int = None) -> list[dict]:
    if count is None:
        count = random.randint(1, 5)
    items = []
    for _ in range(count):
        qty = round(random.uniform(1, 20), 1)
        price = round(random.uniform(25, 500), 2)
        items.append({
            "description": random.choice(LINE_ITEM_DESCRIPTIONS),
            "quantity": qty,
            "unit_price": price,
            "total": round(qty * price, 2),
        })
    return items


# ---------------------------------------------------------------------------
# Data generators
# ---------------------------------------------------------------------------

def generate_vendors(count: int, client_id: str) -> list[dict]:
    now = datetime.now(timezone.utc)
    vendors = []
    names_pool = list(COMPANY_NAMES)
    random.shuffle(names_pool)

    for i in range(count):
        name = names_pool[i % len(names_pool)]
        if i >= len(names_pool):
            name = f"{name} #{i // len(names_pool) + 1}"

        vendors.append({
            "id": str(uuid4()),
            "client_id": client_id,
            "name": name,
            "email_address": _random_email(name),
            "phone": _random_phone(),
            "tax_number": f"{random.randint(10, 99)}-{random.randint(1000000, 9999999)}",
            "is_supplier": True,
            "is_customer": random.random() < 0.2,
            "status": random.choices(["ACTIVE", "ARCHIVED"], weights=[0.85, 0.15])[0],
            "currency": random.choices(["USD", "CAD", "EUR"], weights=[0.8, 0.1, 0.1])[0],
            "address": json.dumps(_random_address()),
            "external_id": None,
            "created_at": now - timedelta(days=random.randint(30, 365)),
            "updated_at": now - timedelta(days=random.randint(0, 30)),
        })

    return vendors


def generate_bills(count: int, client_id: str, vendor_ids: list[str]) -> list[dict]:
    now = datetime.now(timezone.utc)
    bills = []

    for _ in range(count):
        amount = round(random.uniform(100, 50000), 2)
        date = now - timedelta(days=random.randint(0, 90))
        due_date = date + timedelta(days=random.choice([15, 30, 45, 60]))
        status = random.choices(
            ["pending", "paid", "overdue"],
            weights=[0.5, 0.3, 0.2],
        )[0]
        paid_on = (due_date - timedelta(days=random.randint(0, 10))) if status == "paid" else None

        line_items = _random_line_items()
        total = sum(li["total"] for li in line_items)

        bills.append({
            "id": str(uuid4()),
            "client_id": client_id,
            "bill_number": f"BILL-{random.randint(10000, 99999)}",
            "vendor_id": random.choice(vendor_ids) if vendor_ids else None,
            "amount": round(total, 2),
            "date": date,
            "due_date": due_date,
            "paid_on_date": paid_on,
            "description": random.choice(BILL_DESCRIPTIONS),
            "currency": "USD",
            "status": status,
            "line_items": json.dumps(line_items),
            "external_id": None,
            "created_at": date,
            "updated_at": now - timedelta(days=random.randint(0, 10)),
        })

    return bills


def generate_invoices(count: int, client_id: str, vendor_ids: list[str]) -> list[dict]:
    now = datetime.now(timezone.utc)
    invoices = []

    for _ in range(count):
        line_items = _random_line_items()
        sub_total = round(sum(li["total"] for li in line_items), 2)
        tax_rate = random.choice([0, 0.06, 0.075, 0.0825, 0.10])
        total_tax = round(sub_total * tax_rate, 2)
        total_amount = round(sub_total + total_tax, 2)
        balance = total_amount if random.random() > 0.3 else 0

        issue_date = now - timedelta(days=random.randint(0, 90))
        due_date = issue_date + timedelta(days=random.choice([15, 30, 45, 60]))

        if balance == 0:
            status = "PAID"
            paid_on = due_date - timedelta(days=random.randint(0, 15))
        elif random.random() < 0.3:
            status = "SUBMITTED"
            paid_on = None
        else:
            status = "DRAFT"
            paid_on = None

        invoices.append({
            "id": str(uuid4()),
            "client_id": client_id,
            "invoice_number": f"INV-{random.randint(10000, 99999)}",
            "contact_id": random.choice(vendor_ids) if vendor_ids else None,
            "issue_date": issue_date,
            "due_date": due_date,
            "paid_on_date": paid_on,
            "memo": random.choice(INVOICE_MEMOS),
            "currency": "USD",
            "sub_total": sub_total,
            "total_tax_amount": total_tax,
            "total_amount": total_amount,
            "balance": balance,
            "status": status,
            "line_items": json.dumps(line_items),
            "external_id": None,
            "created_at": issue_date,
            "updated_at": now - timedelta(days=random.randint(0, 10)),
        })

    return invoices


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

async def clear_test_data(session: AsyncSession, client_id: str) -> None:
    """Remove existing test data for the client."""
    for table in ("sample_bills", "sample_invoices", "sample_vendors"):
        await session.execute(
            text(f"DELETE FROM {table} WHERE client_id = :cid"),
            {"cid": client_id},
        )
    print(f"  Cleared existing data for client {client_id}")


async def insert_vendors(session: AsyncSession, vendors: list[dict]) -> None:
    for v in vendors:
        await session.execute(
            text("""
                INSERT INTO sample_vendors
                    (id, client_id, name, email_address, phone, tax_number,
                     is_supplier, is_customer, status, currency, address,
                     external_id, created_at, updated_at)
                VALUES
                    (:id, :client_id, :name, :email_address, :phone, :tax_number,
                     :is_supplier, :is_customer, :status, :currency, :address::json,
                     :external_id, :created_at, :updated_at)
            """),
            v,
        )


async def insert_bills(session: AsyncSession, bills: list[dict]) -> None:
    for b in bills:
        await session.execute(
            text("""
                INSERT INTO sample_bills
                    (id, client_id, bill_number, vendor_id, amount, date, due_date,
                     paid_on_date, description, currency, status, line_items,
                     external_id, created_at, updated_at)
                VALUES
                    (:id, :client_id, :bill_number, :vendor_id, :amount, :date, :due_date,
                     :paid_on_date, :description, :currency, :status, :line_items::json,
                     :external_id, :created_at, :updated_at)
            """),
            b,
        )


async def insert_invoices(session: AsyncSession, invoices: list[dict]) -> None:
    for inv in invoices:
        await session.execute(
            text("""
                INSERT INTO sample_invoices
                    (id, client_id, invoice_number, contact_id, issue_date, due_date,
                     paid_on_date, memo, currency, sub_total, total_tax_amount,
                     total_amount, balance, status, line_items,
                     external_id, created_at, updated_at)
                VALUES
                    (:id, :client_id, :invoice_number, :contact_id, :issue_date, :due_date,
                     :paid_on_date, :memo, :currency, :sub_total, :total_tax_amount,
                     :total_amount, :balance, :status, :line_items::json,
                     :external_id, :created_at, :updated_at)
            """),
            inv,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(args: argparse.Namespace) -> None:
    client_id = args.client_id
    db_url = args.db_url

    print(f"\n{'='*60}")
    print(f"  Test Data Generator")
    print(f"  Client ID: {client_id}")
    print(f"  Database:  {db_url.split('@')[1] if '@' in db_url else db_url}")
    print(f"{'='*60}\n")

    # Generate data
    vendors = generate_vendors(args.vendors, client_id)
    vendor_ids = [v["id"] for v in vendors]
    bills = generate_bills(args.bills, client_id, vendor_ids)
    invoices = generate_invoices(args.invoices, client_id, vendor_ids)

    print(f"  Generated:")
    print(f"    Vendors:  {len(vendors)}")
    print(f"    Bills:    {len(bills)}")
    print(f"    Invoices: {len(invoices)}")

    if args.dry_run:
        print(f"\n  [DRY RUN] Sample vendor: {vendors[0]['name']}")
        print(f"  [DRY RUN] Sample bill:   {bills[0]['bill_number']} — ${bills[0]['amount']:,.2f}")
        print(f"  [DRY RUN] Sample invoice: {invoices[0]['invoice_number']} — ${invoices[0]['total_amount']:,.2f}")
        print(f"\n  No data was written to the database.")
        return

    # Write to database
    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        if args.clear:
            await clear_test_data(session, client_id)

        print(f"\n  Inserting records...")
        await insert_vendors(session, vendors)
        print(f"    Vendors inserted:  {len(vendors)}")

        await insert_bills(session, bills)
        print(f"    Bills inserted:    {len(bills)}")

        await insert_invoices(session, invoices)
        print(f"    Invoices inserted: {len(invoices)}")

        await session.commit()

    await engine.dispose()

    total = len(vendors) + len(bills) + len(invoices)
    print(f"\n  Total records created: {total}")
    print(f"  All records have external_id = NULL (ready for outbound sync)")
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate test data in the internal database for sync testing.",
    )
    parser.add_argument(
        "--vendors", type=int, default=10,
        help="Number of vendors to generate (default: 10)",
    )
    parser.add_argument(
        "--bills", type=int, default=20,
        help="Number of bills to generate (default: 20)",
    )
    parser.add_argument(
        "--invoices", type=int, default=15,
        help="Number of invoices to generate (default: 15)",
    )
    parser.add_argument(
        "--client-id", type=str, default=DEFAULT_CLIENT_ID,
        help=f"Client UUID (default: {DEFAULT_CLIENT_ID})",
    )
    parser.add_argument(
        "--db-url", type=str, default=DEFAULT_DB_URL,
        help="Internal database connection URL",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be generated without writing to DB",
    )
    parser.add_argument(
        "--clear", action="store_true",
        help="Clear existing test data before inserting",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))

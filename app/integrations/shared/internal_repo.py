"""Repository for accessing synced entity data tables.

In this demo, the sample data tables live in the same database as the
integration platform.  In a real deployment, swap this class for an
API client that talks to the internal system's REST API — the sync
strategy only depends on the public methods defined here.
"""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from app.core.logging import get_logger
from app.infrastructure.db.database import get_session_factory

logger = get_logger(__name__)


def _get_session_factory():
    return get_session_factory()


class InternalDataRepository:
    """Access to the internal system's data tables (job_runner database)."""

    # ------------------------------------------------------------------
    # Vendors
    # ------------------------------------------------------------------

    async def get_vendors(
        self,
        client_id: UUID,
        since: datetime | None = None,
        record_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get vendors from the internal system."""
        factory = _get_session_factory()
        async with factory() as session:
            conditions = ["client_id = :client_id"]
            params: dict[str, Any] = {"client_id": str(client_id)}

            if since:
                conditions.append("updated_at > :since")
                params["since"] = since

            if record_ids:
                conditions.append("id = ANY(:record_ids)")
                params["record_ids"] = record_ids

            where = " AND ".join(conditions)
            result = await session.execute(
                text(f"SELECT * FROM sample_vendors WHERE {where} ORDER BY created_at"),
                params,
            )
            rows = result.mappings().all()
            return [self._row_to_dict(row) for row in rows]

    async def upsert_vendor(
        self, client_id: UUID, data: dict[str, Any], record_id: str | None = None
    ) -> str:
        """Create or update a vendor. Returns the internal record ID."""
        factory = _get_session_factory()
        now = datetime.now(UTC)

        async with factory() as session:
            if record_id:
                # Update existing record
                address_json = json.dumps(data.get("address")) if data.get("address") else None
                await session.execute(
                    text(
                        """
                        UPDATE sample_vendors SET
                            name = COALESCE(:name, name),
                            email_address = COALESCE(:email, email_address),
                            phone = COALESCE(:phone, phone),
                            tax_number = COALESCE(:tax_number, tax_number),
                            is_supplier = :is_supplier,
                            is_customer = :is_customer,
                            status = COALESCE(:status, status),
                            currency = COALESCE(:currency, currency),
                            address = COALESCE(CAST(:address AS json), address),
                            updated_at = :now
                        WHERE id = :id
                    """
                    ),
                    {
                        "id": record_id,
                        "name": data.get("name"),
                        "email": data.get("email_address"),
                        "phone": data.get("phone"),
                        "tax_number": data.get("tax_number"),
                        "is_supplier": data.get("is_supplier", True),
                        "is_customer": data.get("is_customer", False),
                        "status": data.get("status"),
                        "currency": data.get("currency"),
                        "address": address_json,
                        "now": now,
                    },
                )
            else:
                # Insert new record
                record_id = str(uuid4())
                address_json = json.dumps(data.get("address")) if data.get("address") else None
                await session.execute(
                    text(
                        """
                        INSERT INTO sample_vendors
                            (id, client_id, name, email_address, phone, tax_number,
                             is_supplier, is_customer, status, currency, address,
                             created_at, updated_at)
                        VALUES
                            (:id, :client_id, :name, :email, :phone, :tax_number,
                             :is_supplier, :is_customer, :status, :currency, CAST(:address AS json),
                             :now, :now)
                    """
                    ),
                    {
                        "id": record_id,
                        "client_id": str(client_id),
                        "name": data.get("name", "Unknown Vendor"),
                        "email": data.get("email_address"),
                        "phone": data.get("phone"),
                        "tax_number": data.get("tax_number"),
                        "is_supplier": data.get("is_supplier", True),
                        "is_customer": data.get("is_customer", False),
                        "status": data.get("status", "ACTIVE"),
                        "currency": data.get("currency", "USD"),
                        "address": address_json,
                        "now": now,
                    },
                )

            await session.commit()
            return record_id

    # ------------------------------------------------------------------
    # Bills
    # ------------------------------------------------------------------

    async def get_bills(
        self,
        client_id: UUID,
        since: datetime | None = None,
        record_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get bills from the internal system."""
        factory = _get_session_factory()
        async with factory() as session:
            conditions = ["client_id = :client_id"]
            params: dict[str, Any] = {"client_id": str(client_id)}

            if since:
                conditions.append("updated_at > :since")
                params["since"] = since

            if record_ids:
                conditions.append("id = ANY(:record_ids)")
                params["record_ids"] = record_ids

            where = " AND ".join(conditions)
            result = await session.execute(
                text(f"SELECT * FROM sample_bills WHERE {where} ORDER BY created_at"),
                params,
            )
            rows = result.mappings().all()
            return [self._row_to_dict(row) for row in rows]

    async def upsert_bill(
        self, client_id: UUID, data: dict[str, Any], record_id: str | None = None
    ) -> str:
        """Create or update a bill. Returns the internal record ID."""
        factory = _get_session_factory()
        now = datetime.now(UTC)

        async with factory() as session:
            line_items_json = json.dumps(data.get("line_items")) if data.get("line_items") else None

            if record_id:
                # Update existing record
                await session.execute(
                    text(
                        """
                        UPDATE sample_bills SET
                            bill_number = COALESCE(:bill_number, bill_number),
                            amount = COALESCE(:amount, amount),
                            date = COALESCE(:date, date),
                            due_date = COALESCE(:due_date, due_date),
                            paid_on_date = :paid_on_date,
                            description = COALESCE(:description, description),
                            currency = COALESCE(:currency, currency),
                            status = COALESCE(:status, status),
                            line_items = COALESCE(CAST(:line_items AS json), line_items),
                            updated_at = :now
                        WHERE id = :id
                    """
                    ),
                    {
                        "id": record_id,
                        "bill_number": data.get("bill_number"),
                        "amount": data.get("amount"),
                        "date": data.get("date", now),
                        "due_date": data.get("due_date"),
                        "paid_on_date": data.get("paid_on_date"),
                        "description": data.get("description"),
                        "currency": data.get("currency"),
                        "status": data.get("status"),
                        "line_items": line_items_json,
                        "now": now,
                    },
                )
            else:
                # Insert new record
                record_id = str(uuid4())
                vendor_id = data.get("vendor_id")

                await session.execute(
                    text(
                        """
                        INSERT INTO sample_bills
                            (id, client_id, bill_number, vendor_id, amount, date, due_date,
                             paid_on_date, description, currency, status, line_items,
                             created_at, updated_at)
                        VALUES
                            (:id, :client_id, :bill_number, :vendor_id, :amount, :date, :due_date,
                             :paid_on_date, :description, :currency, :status, CAST(:line_items AS json),
                             :now, :now)
                    """
                    ),
                    {
                        "id": record_id,
                        "client_id": str(client_id),
                        "bill_number": data.get("bill_number"),
                        "vendor_id": vendor_id,
                        "amount": data.get("amount", 0),
                        "date": data.get("date", now),
                        "due_date": data.get("due_date"),
                        "paid_on_date": data.get("paid_on_date"),
                        "description": data.get("description"),
                        "currency": data.get("currency", "USD"),
                        "status": data.get("status", "pending"),
                        "line_items": line_items_json,
                        "now": now,
                    },
                )

            await session.commit()
            return record_id

    # ------------------------------------------------------------------
    # Invoices
    # ------------------------------------------------------------------

    async def get_invoices(
        self,
        client_id: UUID,
        since: datetime | None = None,
        record_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get invoices from the internal system."""
        factory = _get_session_factory()
        async with factory() as session:
            conditions = ["client_id = :client_id"]
            params: dict[str, Any] = {"client_id": str(client_id)}

            if since:
                conditions.append("updated_at > :since")
                params["since"] = since

            if record_ids:
                conditions.append("id = ANY(:record_ids)")
                params["record_ids"] = record_ids

            where = " AND ".join(conditions)
            result = await session.execute(
                text(f"SELECT * FROM sample_invoices WHERE {where} ORDER BY created_at"),
                params,
            )
            rows = result.mappings().all()
            return [self._row_to_dict(row) for row in rows]

    async def upsert_invoice(
        self, client_id: UUID, data: dict[str, Any], record_id: str | None = None
    ) -> str:
        """Create or update an invoice. Returns the internal record ID."""
        factory = _get_session_factory()
        now = datetime.now(UTC)

        async with factory() as session:
            line_items_json = json.dumps(data.get("line_items")) if data.get("line_items") else None

            if record_id:
                # Update existing record
                await session.execute(
                    text(
                        """
                        UPDATE sample_invoices SET
                            invoice_number = COALESCE(:invoice_number, invoice_number),
                            issue_date = COALESCE(:issue_date, issue_date),
                            due_date = COALESCE(:due_date, due_date),
                            paid_on_date = :paid_on_date,
                            memo = COALESCE(:memo, memo),
                            currency = COALESCE(:currency, currency),
                            sub_total = COALESCE(:sub_total, sub_total),
                            total_tax_amount = COALESCE(:total_tax, total_tax_amount),
                            total_amount = COALESCE(:total_amount, total_amount),
                            balance = COALESCE(:balance, balance),
                            status = COALESCE(:status, status),
                            line_items = COALESCE(CAST(:line_items AS json), line_items),
                            updated_at = :now
                        WHERE id = :id
                    """
                    ),
                    {
                        "id": record_id,
                        "invoice_number": data.get("invoice_number"),
                        "issue_date": data.get("issue_date"),
                        "due_date": data.get("due_date"),
                        "paid_on_date": data.get("paid_on_date"),
                        "memo": data.get("memo"),
                        "currency": data.get("currency"),
                        "sub_total": data.get("sub_total"),
                        "total_tax": data.get("total_tax_amount"),
                        "total_amount": data.get("total_amount"),
                        "balance": data.get("balance"),
                        "status": data.get("status"),
                        "line_items": line_items_json,
                        "now": now,
                    },
                )
            else:
                # Insert new record
                record_id = str(uuid4())
                contact_id = data.get("contact_id")

                await session.execute(
                    text(
                        """
                        INSERT INTO sample_invoices
                            (id, client_id, invoice_number, contact_id, issue_date, due_date,
                             paid_on_date, memo, currency, sub_total, total_tax_amount,
                             total_amount, balance, status, line_items,
                             created_at, updated_at)
                        VALUES
                            (:id, :client_id, :invoice_number, :contact_id, :issue_date, :due_date,
                             :paid_on_date, :memo, :currency, :sub_total, :total_tax,
                             :total_amount, :balance, :status, CAST(:line_items AS json),
                             :now, :now)
                    """
                    ),
                    {
                        "id": record_id,
                        "client_id": str(client_id),
                        "invoice_number": data.get("invoice_number"),
                        "contact_id": contact_id,
                        "issue_date": data.get("issue_date"),
                        "due_date": data.get("due_date"),
                        "paid_on_date": data.get("paid_on_date"),
                        "memo": data.get("memo"),
                        "currency": data.get("currency", "USD"),
                        "sub_total": data.get("sub_total", 0),
                        "total_tax": data.get("total_tax_amount", 0),
                        "total_amount": data.get("total_amount", 0),
                        "balance": data.get("balance", 0),
                        "status": data.get("status", "DRAFT"),
                        "line_items": line_items_json,
                        "now": now,
                    },
                )

            await session.commit()
            return record_id

    # ------------------------------------------------------------------
    # Chart of Accounts
    # ------------------------------------------------------------------

    async def get_chart_of_accounts(
        self,
        client_id: UUID,
        since: datetime | None = None,
        record_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get chart of accounts from the internal system."""
        factory = _get_session_factory()
        async with factory() as session:
            conditions = ["client_id = :client_id"]
            params: dict[str, Any] = {"client_id": str(client_id)}

            if since:
                conditions.append("updated_at > :since")
                params["since"] = since

            if record_ids:
                conditions.append("id = ANY(:record_ids)")
                params["record_ids"] = record_ids

            where = " AND ".join(conditions)
            result = await session.execute(
                text(f"SELECT * FROM sample_chart_of_accounts WHERE {where} ORDER BY created_at"),
                params,
            )
            rows = result.mappings().all()
            return [self._row_to_dict(row) for row in rows]

    async def upsert_chart_of_accounts(
        self, client_id: UUID, data: dict[str, Any], record_id: str | None = None
    ) -> str:
        """Create or update a chart of accounts record. Returns the internal record ID."""
        factory = _get_session_factory()
        now = datetime.now(UTC)

        async with factory() as session:
            if record_id:
                # Update existing record
                await session.execute(
                    text(
                        """
                        UPDATE sample_chart_of_accounts SET
                            name = COALESCE(:name, name),
                            account_number = COALESCE(:account_number, account_number),
                            account_type = COALESCE(:account_type, account_type),
                            account_sub_type = COALESCE(:account_sub_type, account_sub_type),
                            classification = COALESCE(:classification, classification),
                            current_balance = COALESCE(:current_balance, current_balance),
                            currency = COALESCE(:currency, currency),
                            description = COALESCE(:description, description),
                            active = :active,
                            parent_account_external_id = :parent_account_external_id,
                            updated_at = :now
                        WHERE id = :id
                    """
                    ),
                    {
                        "id": record_id,
                        "name": data.get("name"),
                        "account_number": data.get("account_number"),
                        "account_type": data.get("account_type"),
                        "account_sub_type": data.get("account_sub_type"),
                        "classification": data.get("classification"),
                        "current_balance": data.get("current_balance"),
                        "currency": data.get("currency"),
                        "description": data.get("description"),
                        "active": data.get("active", True),
                        "parent_account_external_id": data.get("parent_account_external_id"),
                        "now": now,
                    },
                )
            else:
                # Insert new record
                record_id = str(uuid4())
                await session.execute(
                    text(
                        """
                        INSERT INTO sample_chart_of_accounts
                            (id, client_id, name, account_number, account_type, account_sub_type,
                             classification, current_balance, currency, description, active,
                             parent_account_external_id, created_at, updated_at)
                        VALUES
                            (:id, :client_id, :name, :account_number, :account_type, :account_sub_type,
                             :classification, :current_balance, :currency, :description, :active,
                             :parent_account_external_id, :now, :now)
                    """
                    ),
                    {
                        "id": record_id,
                        "client_id": str(client_id),
                        "name": data.get("name", "Unknown Account"),
                        "account_number": data.get("account_number"),
                        "account_type": data.get("account_type", ""),
                        "account_sub_type": data.get("account_sub_type"),
                        "classification": data.get("classification"),
                        "current_balance": data.get("current_balance", 0),
                        "currency": data.get("currency", "USD"),
                        "description": data.get("description"),
                        "active": data.get("active", True),
                        "parent_account_external_id": data.get("parent_account_external_id"),
                        "now": now,
                    },
                )

            await session.commit()
            return record_id

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row) -> dict[str, Any]:
        """Convert a SQLAlchemy Row to a plain dict with serializable values."""
        result = dict(row)
        for key, val in result.items():
            if isinstance(val, UUID):
                result[key] = str(val)
            elif isinstance(val, datetime):
                result[key] = val.isoformat()
        return result

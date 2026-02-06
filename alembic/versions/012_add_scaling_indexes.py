"""Add scaling indexes for billion-row performance.

Revision ID: 012
Revises: 011
Create Date: 2025-02-06

This migration adds missing indexes critical for query performance at scale:

1. integration_state: Composite index for get_pending_records query
2. sync_jobs: Composite index for create_job_if_no_running query
3. integration_history: BRIN index for time-range cleanup queries

It also sets up native PostgreSQL partitioning for integration_state by client_id.
This enables partition pruning and makes per-client operations efficient at scale.

NOTE: The partitioning migration requires a brief maintenance window as it:
- Creates a new partitioned table
- Migrates existing data
- Swaps table names

For zero-downtime, consider using pg_partman or logical replication instead.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # 1. Add missing index for get_pending_records / get_records_by_status
    # =========================================================================
    # Current query: WHERE client_id = ? AND integration_id = ? AND entity_type = ? AND sync_status = 'pending'
    # Old index only had (client_id, sync_status) - missing integration_id and entity_type

    # Drop the old partial index that's insufficient
    op.drop_index("ix_integration_state_pending", table_name="integration_state")

    # Create a better composite index for pending/failed record lookups
    # This covers the full WHERE clause of get_pending_records
    op.create_index(
        "ix_integration_state_pending_v2",
        "integration_state",
        ["client_id", "integration_id", "entity_type", "sync_status"],
        postgresql_where=sa.text("sync_status IN ('pending', 'failed')"),
    )

    # =========================================================================
    # 2. sync_jobs composite index
    # =========================================================================
    # NOTE: ix_sync_jobs_running_check already exists from migration 005
    # It covers: (client_id, integration_id, status) WHERE status IN ('pending', 'running')
    # No additional index needed.

    # =========================================================================
    # 3. Replace B-tree with BRIN index for integration_history cleanup
    # =========================================================================
    # BRIN is much more efficient for append-only tables with time-ordered data
    # Reduces index size by ~100x while still enabling efficient range scans
    op.drop_index("ix_integration_history_created", table_name="integration_history")

    op.execute("""
        CREATE INDEX ix_integration_history_created_brin
        ON integration_history USING brin (created_at)
        WITH (pages_per_range = 128)
    """)

    # =========================================================================
    # 4. Set up native PostgreSQL partitioning for integration_state
    # =========================================================================
    # This is the most impactful change for billion-row scale.
    # We use HASH partitioning by client_id for even distribution.

    # Step 4a: Create the new partitioned table
    # Use explicit UUID type casting to ensure compatibility
    op.execute("""
        CREATE TABLE integration_state_partitioned (
            id UUID NOT NULL,
            client_id UUID NOT NULL,
            integration_id UUID NOT NULL,
            entity_type VARCHAR(50) NOT NULL,
            internal_record_id VARCHAR(255),
            external_record_id VARCHAR(255),
            sync_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            sync_direction VARCHAR(10),
            internal_version_id INTEGER NOT NULL DEFAULT 1,
            external_version_id INTEGER NOT NULL DEFAULT 0,
            last_sync_version_id INTEGER NOT NULL DEFAULT 0,
            last_synced_at TIMESTAMP WITH TIME ZONE,
            last_job_id UUID,
            error_code VARCHAR(50),
            error_message TEXT,
            error_details JSONB,
            metadata JSONB,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            PRIMARY KEY (client_id, id)
        ) PARTITION BY HASH (client_id)
    """)

    # Step 4b: Create 16 hash partitions (can be increased later)
    # 16 partitions is a good starting point - can handle billions of rows
    # and allows parallel query execution across partitions
    for i in range(16):
        op.execute(f"""
            CREATE TABLE integration_state_p{i:02d}
            PARTITION OF integration_state_partitioned
            FOR VALUES WITH (MODULUS 16, REMAINDER {i})
        """)

    # Step 4c: Create indexes on the partitioned table
    # These will be automatically created on each partition
    op.execute("""
        CREATE UNIQUE INDEX uq_integration_state_part_internal
        ON integration_state_partitioned (client_id, integration_id, entity_type, internal_record_id)
        WHERE internal_record_id IS NOT NULL
    """)

    op.execute("""
        CREATE UNIQUE INDEX uq_integration_state_part_external
        ON integration_state_partitioned (client_id, integration_id, entity_type, external_record_id)
        WHERE external_record_id IS NOT NULL
    """)

    op.execute("""
        CREATE INDEX ix_integration_state_part_pending
        ON integration_state_partitioned (client_id, integration_id, entity_type, sync_status)
        WHERE sync_status IN ('pending', 'failed')
    """)

    op.execute("""
        CREATE INDEX ix_integration_state_part_job
        ON integration_state_partitioned (client_id, last_job_id)
        WHERE last_job_id IS NOT NULL
    """)

    # Step 4d: Migrate data from old table to partitioned table
    # Explicitly list columns to avoid type inference issues
    op.execute("""
        INSERT INTO integration_state_partitioned (
            id, client_id, integration_id, entity_type,
            internal_record_id, external_record_id,
            sync_status, sync_direction,
            internal_version_id, external_version_id, last_sync_version_id,
            last_synced_at, last_job_id,
            error_code, error_message, error_details,
            metadata, created_at, updated_at
        )
        SELECT
            id::uuid, client_id::uuid, integration_id::uuid, entity_type,
            internal_record_id, external_record_id,
            sync_status, sync_direction,
            internal_version_id, external_version_id, last_sync_version_id,
            last_synced_at, last_job_id::uuid,
            error_code, error_message, error_details,
            metadata, created_at, updated_at
        FROM integration_state
    """)

    # Step 4e: Swap tables
    op.execute("ALTER TABLE integration_state RENAME TO integration_state_old")
    op.execute("ALTER TABLE integration_state_partitioned RENAME TO integration_state")

    # Step 4f: Drop old table (can be deferred if you want to verify first)
    # Uncomment the next line after verifying the migration succeeded
    # op.execute("DROP TABLE integration_state_old")

    # For safety, we keep the old table. Drop it manually after verification:
    # DROP TABLE integration_state_old;


def downgrade() -> None:
    # =========================================================================
    # Reverse partitioning (create regular table, migrate data back)
    # =========================================================================

    # Check if old table still exists (wasn't dropped)
    # If it exists, just swap back. If not, we need to recreate.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'integration_state_old') THEN
                -- Old table exists, just swap back
                DROP TABLE integration_state CASCADE;
                ALTER TABLE integration_state_old RENAME TO integration_state;
            ELSE
                -- Need to recreate from partitioned table
                CREATE TABLE integration_state_new (
                    id UUID NOT NULL,
                    client_id UUID NOT NULL,
                    integration_id UUID NOT NULL,
                    entity_type VARCHAR(50) NOT NULL,
                    internal_record_id VARCHAR(255),
                    external_record_id VARCHAR(255),
                    sync_status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    sync_direction VARCHAR(10),
                    internal_version_id INTEGER NOT NULL DEFAULT 1,
                    external_version_id INTEGER NOT NULL DEFAULT 0,
                    last_sync_version_id INTEGER NOT NULL DEFAULT 0,
                    last_synced_at TIMESTAMP WITH TIME ZONE,
                    last_job_id UUID,
                    error_code VARCHAR(50),
                    error_message TEXT,
                    error_details JSONB,
                    metadata JSONB,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (client_id, id)
                );

                INSERT INTO integration_state_new SELECT * FROM integration_state;
                DROP TABLE integration_state CASCADE;
                ALTER TABLE integration_state_new RENAME TO integration_state;
            END IF;
        END $$
    """)

    # Recreate original indexes
    op.create_index(
        "ix_integration_state_lookup",
        "integration_state",
        ["client_id", "integration_id", "entity_type", "internal_record_id"],
    )

    op.create_index(
        "ix_integration_state_pending",
        "integration_state",
        ["client_id", "sync_status"],
        postgresql_where=sa.text("sync_status IN ('pending', 'failed')"),
    )

    op.execute("""
        CREATE UNIQUE INDEX uq_integration_state_internal
        ON integration_state (client_id, integration_id, entity_type, internal_record_id)
        WHERE internal_record_id IS NOT NULL
    """)

    op.execute("""
        CREATE UNIQUE INDEX uq_integration_state_external
        ON integration_state (client_id, integration_id, entity_type, external_record_id)
        WHERE external_record_id IS NOT NULL
    """)

    op.execute("""
        CREATE INDEX ix_integration_state_job
        ON integration_state (client_id, last_job_id)
        WHERE last_job_id IS NOT NULL
    """)

    # =========================================================================
    # Reverse integration_history BRIN back to B-tree
    # =========================================================================
    op.drop_index("ix_integration_history_created_brin", table_name="integration_history")
    op.create_index(
        "ix_integration_history_created",
        "integration_history",
        ["created_at"],
    )

    # =========================================================================
    # Reverse the pending index change
    # =========================================================================
    op.drop_index("ix_integration_state_pending_v2", table_name="integration_state")
    op.create_index(
        "ix_integration_state_pending",
        "integration_state",
        ["client_id", "sync_status"],
        postgresql_where=sa.text("sync_status IN ('pending', 'failed')"),
    )

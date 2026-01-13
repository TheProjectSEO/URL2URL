URL-to-URL Supabase Migrations

Overview

- This folder snapshots the current Supabase schema and RPCs used by the API.
- The live database was provisioned via Supabase MCP; these SQL files provide
  version control, onboarding, and disaster recovery.

Usage

- Apply files in numeric order (0001, 0002, ...). Adjust for your environment.
- Ensure pgvector extension is enabled.

Notes

- These definitions mirror the schema described in CLAUDE.md and the RPC names
  used in apps/api/services/supabase.py and matcher_v2.
- If your Supabase already has these objects, re-running “CREATE IF NOT EXISTS”
  statements is safe; “CREATE OR REPLACE FUNCTION” will sync RPCs.


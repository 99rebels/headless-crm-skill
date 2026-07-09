// core/db.ts — the Supabase client, initialised by each adapter (not from import-time env,
// so the same core runs on Node/stdio AND on Cloudflare Workers).
// Uses the service-role key (server-only, bypasses RLS). The core scopes every query by
// workspace_id until real RLS policies land (auth workstream).

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let _db: SupabaseClient | null = null;

/** Call once at adapter startup with the environment's Supabase URL + service-role key. */
export function initDb(url: string, serviceKey: string): SupabaseClient {
  if (!url || !serviceKey) {
    throw new Error("initDb: missing Supabase URL or service-role key.");
  }
  _db = createClient(url, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return _db;
}

/** Get the initialised client. Throws if an adapter forgot to call initDb first. */
export function getDb(): SupabaseClient {
  if (!_db) throw new Error("DB not initialised — call initDb(url, serviceKey) at startup.");
  return _db;
}

/** Narrow Supabase's error into a thrown Error so callers can use try/catch uniformly. */
export function orThrow<T>(res: { data: T | null; error: { message: string } | null }): T {
  if (res.error) throw new Error(res.error.message);
  if (res.data === null) throw new Error("No data returned");
  return res.data;
}

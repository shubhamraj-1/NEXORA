-- Read-only RLS audit for NEXORA.
-- Run in the Supabase SQL Editor. This file does not change any data or policy.

-- 1. RLS state for application tables.
select
  tablename,
  rowsecurity,
  forcetable
from pg_tables
where schemaname = 'public'
  and tablename in ('profiles', 'runs', 'tasks', 'task_logs', 'task_results')
order by tablename;

-- 2. Policies on application tables.
select
  tablename,
  policyname,
  permissive,
  roles,
  cmd,
  qual,
  with_check
from pg_policies
where schemaname = 'public'
  and tablename in ('profiles', 'runs', 'tasks', 'task_logs', 'task_results')
order by tablename, policyname;

-- 3. Private screenshot bucket.
select id, name, public
from storage.buckets
where id = 'generated-files';

-- 4. Storage object policies for that bucket.
select
  policyname,
  permissive,
  roles,
  cmd,
  qual,
  with_check
from pg_policies
where schemaname = 'storage'
  and tablename = 'objects'
  and policyname like 'generated files%'
order by policyname;

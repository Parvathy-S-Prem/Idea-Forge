-- Run once in the Supabase SQL editor.
create extension if not exists vector;

create table if not exists complaints (
  id uuid primary key default gen_random_uuid(),
  ref text unique not null,
  source text not null,                 -- telegram | web
  chat_id bigint,                       -- telegram chat (null for web)
  raw_text text,
  media_url text,
  media_mime text,
  lat double precision,
  lon double precision,
  status text not null default 'new',   -- new|processing|registered|review|rejected|replied
  category text,
  department text,
  sla_hours int,
  ward text,
  zone text,
  summary text,
  transcript text,
  reply_language text,                  -- ta | en
  confidence real,
  review_reason text,
  cluster_id uuid,
  embedding vector(768),
  created_at timestamptz not null default now(),
  claimed_at timestamptz,
  processed_at timestamptz
);
create index if not exists complaints_status_idx on complaints(status);
create index if not exists complaints_chat_idx on complaints(chat_id, created_at desc);

create table if not exists clusters (
  id uuid primary key default gen_random_uuid(),
  ref text,                             -- ref of first complaint
  ward text,
  zone text,
  category text,
  department text,
  summary text,
  lat double precision,
  lon double precision,
  report_count int not null default 1,
  due_at timestamptz,
  draft_reply text,
  reply_language text,
  status text not null default 'open',  -- open|replied
  created_at timestamptz not null default now(),
  replied_at timestamptz
);

create table if not exists agent_log (
  id bigserial primary key,
  complaint_id uuid references complaints(id) on delete cascade,
  step int,
  tool text,
  args jsonb,
  result jsonb,
  created_at timestamptz not null default now()
);
create index if not exists agent_log_c_idx on agent_log(complaint_id, id);

create table if not exists settings (key text primary key, value text);

create or replace function match_complaints(
  query_embedding vector(768), p_ward text, match_threshold float, match_count int
) returns table (id uuid, ref text, summary text, category text, cluster_id uuid, similarity float)
language sql stable as $$
  select c.id, c.ref, c.summary, c.category, c.cluster_id,
         1 - (c.embedding <=> query_embedding) as similarity
  from complaints c
  where c.ward = p_ward and c.status in ('registered','replied') and c.embedding is not null
    and 1 - (c.embedding <=> query_embedding) > match_threshold
  order by c.embedding <=> query_embedding
  limit match_count
$$;

insert into storage.buckets (id, name, public) values ('media', 'media', true)
on conflict (id) do nothing;

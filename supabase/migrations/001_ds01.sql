-- DS01: run in a dedicated Supabase project. No public access.
begin;
insert into storage.buckets(id,name,public,file_size_limit)
values ('stock-bot-private','stock-bot-private',false,49283072)
on conflict (id) do nothing;
do $$ begin
 if exists(select 1 from storage.buckets where id='stock-bot-private' and public) then
  raise exception 'DS01 requires a private bucket';
 end if;
end $$;
create table if not exists public.ds01_versions (
 namespace text not null check(namespace ~ '^[a-z0-9-]{1,40}$'),
 kind text not null check(kind in ('reference','paper','scan','single','preferences')),
 version bigint not null check(version > 0),
 sha text not null check(sha ~ '^[0-9a-f]{64}$'),
 size_bytes bigint not null check(size_bytes between 1 and 49283072),
 created_at timestamptz not null default now(),
 primary key(namespace,kind,version)
);
create table if not exists public.ds01_heads (
 namespace text not null,
 kind text not null,
 version bigint not null,
 primary key(namespace,kind),
 foreign key(namespace,kind,version) references public.ds01_versions(namespace,kind,version)
);
alter table public.ds01_versions enable row level security;
alter table public.ds01_heads enable row level security;
revoke all on public.ds01_versions,public.ds01_heads from public,anon,authenticated;
grant select,insert on public.ds01_versions to service_role;
grant select,insert,update on public.ds01_heads to service_role;
-- Only the server role may commit. Storage upload and metadata commit are distinct.
create or replace function public.ds01_commit(p_namespace text,p_kind text,p_expected bigint,p_sha text,p_size bigint)
returns bigint language plpgsql security invoker set search_path = '' as $$
declare v bigint; current_sha text;
begin
 if p_namespace !~ '^[a-z0-9-]{1,40}$' or p_kind not in ('reference','paper','scan','single','preferences')
    or p_sha !~ '^[0-9a-f]{64}$' or p_size not between 1 and 49283072 or p_expected < 0 then
    raise exception 'Invalid DS01 input';
 end if;
 perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_namespace||':'||p_kind,0));
 select h.version,s.sha into v,current_sha from public.ds01_heads h
 join public.ds01_versions s using(namespace,kind,version)
 where h.namespace=p_namespace and h.kind=p_kind;
 v:=coalesce(v,0);
 if current_sha=p_sha then return v; end if;
 if v<>p_expected then return -1; end if;
 -- Check private object exists; no update or delete through this RPC.
 if not exists(select 1 from storage.objects where bucket_id='stock-bot-private'
 and name=p_namespace||'/'||p_kind||'/'||p_sha) then raise exception 'Missing DS01 object'; end if;
 insert into public.ds01_versions(namespace,kind,version,sha,size_bytes)
 values(p_namespace,p_kind,v+1,p_sha,p_size);
 insert into public.ds01_heads(namespace,kind,version) values(p_namespace,p_kind,v+1)
 on conflict(namespace,kind) do update set version=excluded.version;
 return v+1;
end $$;
revoke all on function public.ds01_commit(text,text,bigint,text,bigint) from public,anon,authenticated;
grant execute on function public.ds01_commit(text,text,bigint,text,bigint) to service_role;
-- Usage includes orphan objects; limit applies to dedicated project, dashboard authoritative.
create or replace function public.ds01_usage(p_namespace text)
returns bigint language sql stable security invoker set search_path='' as $$
 select coalesce(sum(case when metadata->>'size' ~ '^[0-9]+$' then (metadata->>'size')::bigint else 0 end),0)::bigint
 from storage.objects where bucket_id='stock-bot-private' and name like p_namespace||'/%'
$$;
revoke all on function public.ds01_usage(text) from public,anon,authenticated;
grant execute on function public.ds01_usage(text) to service_role;
create table if not exists public.ds01_sync_logs (
 id bigint generated always as identity primary key,
 namespace text not null check(namespace ~ '^[a-z0-9-]{1,40}$'),
 kind text not null check(kind in ('reference','paper','scan','single','preferences')),
 result text not null check(result in ('saved','failed')),
 created_at timestamptz not null default now()
);
alter table public.ds01_sync_logs enable row level security;
revoke all on public.ds01_sync_logs from public,anon,authenticated;
grant select,insert on public.ds01_sync_logs to service_role;
grant usage,select on sequence public.ds01_sync_logs_id_seq to service_role;
commit;

-- GGM 3D Configurator schema.
-- Paste into the Supabase SQL editor and run by hand.

create extension if not exists "pgcrypto";

create table if not exists public.products (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  category text not null,
  width_mm int not null,
  depth_mm int not null,
  height_mm int not null,
  image_url text default '',
  description text default '',
  created_at timestamptz not null default now()
);

create table if not exists public.models (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.products (id) on delete cascade,
  method text not null check (method in ('parametric', 'ai')),
  status text not null default 'pending'
    check (status in ('pending', 'running', 'ready', 'failed')),
  glb_url text default '',
  spec_json jsonb,
  error text default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- one model per product; upsert target for storage.save_model
create unique index if not exists models_product_id_key
  on public.models (product_id);

-- RLS: public read, writes only through the service key on the server
-- (the service key bypasses RLS, so no write policies are defined).
alter table public.products enable row level security;
alter table public.models enable row level security;

drop policy if exists "public read products" on public.products;
create policy "public read products"
  on public.products for select using (true);

drop policy if exists "public read models" on public.models;
create policy "public read models"
  on public.models for select using (true);

-- Storage bucket "models" with public read access.
-- AR needs a public HTTPS GLB URL, the public bucket provides it.
insert into storage.buckets (id, name, public)
values ('models', 'models', true)
on conflict (id) do update set public = true;

drop policy if exists "public read model files" on storage.objects;
create policy "public read model files"
  on storage.objects for select using (bucket_id = 'models');

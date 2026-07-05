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
  usdz_url text default '',
  spec_json jsonb,
  error text default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- iPhone AR: USDZ variant of the GLB, served to Quick Look via ios-src.
-- No-op on fresh databases (column is in the create above); migrates old ones.
alter table public.models add column if not exists usdz_url text default '';

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

-- Cleanup: the single-basin sink was retired in favor of the double sink
-- (product ...0007). Idempotent; the models row would also go via the FK
-- cascade, but the explicit delete keeps the intent readable.
delete from public.models
  where product_id = '0b6f9c1a-1111-4a01-8a01-000000000003';
delete from public.products
  where id = '0b6f9c1a-1111-4a01-8a01-000000000003';
delete from storage.objects
  where bucket_id = 'models'
    and name in ('0b6f9c1a-1111-4a01-8a01-000000000003.glb',
                 '0b6f9c1a-1111-4a01-8a01-000000000003.usdz');

-- Work table matched to the real GGM product (600x700x850). The cached
-- spec and GLB still describe the old 1200 mm table, so drop the models
-- row and stored files; the next Generate rebuilds at the new size.
update public.products
  set name      = 'Commercial Stainless Steel Centre Table PREMIUM - 600x700mm - with Undershelf',
      width_mm  = 600,
      depth_mm  = 700,
      height_mm = 850
  where id = '0b6f9c1a-1111-4a01-8a01-000000000001';
delete from public.models
  where product_id = '0b6f9c1a-1111-4a01-8a01-000000000001';
delete from storage.objects
  where bucket_id = 'models'
    and name in ('0b6f9c1a-1111-4a01-8a01-000000000001.glb',
                 '0b6f9c1a-1111-4a01-8a01-000000000001.usdz');

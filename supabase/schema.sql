-- Price Tracker — Supabase schema + row-level security.
-- Run this once in your Supabase project: SQL Editor → paste → Run.

-- ── Tables ──────────────────────────────────────────────────────────────────
create table if not exists public.products (
    id              bigint generated always as identity primary key,
    user_id         uuid not null references auth.users (id) on delete cascade,
    url             text not null,
    retailer        text not null default '',
    name            text,
    currency        text not null default '',
    last_price      double precision,
    last_stock      text,
    prev_price      double precision,
    prev_stock      text,
    price_changed   boolean not null default false,
    stock_changed   boolean not null default false,
    position        integer not null default 0,
    created_at      timestamptz not null default now(),
    last_checked    timestamptz
);
create index if not exists products_user_idx on public.products (user_id);

-- Migration for existing projects: add the manual-ordering column if missing.
alter table public.products add column if not exists position integer not null default 0;

create table if not exists public.price_history (
    id            bigint generated always as identity primary key,
    product_id    bigint not null references public.products (id) on delete cascade,
    price         double precision,
    stock         text,
    captured_at   timestamptz not null default now()
);
create index if not exists price_history_product_idx
    on public.price_history (product_id, captured_at);

-- ── Row-level security ──────────────────────────────────────────────────────
alter table public.products enable row level security;
alter table public.price_history enable row level security;

-- Users can only touch their own products.
drop policy if exists "own products" on public.products;
create policy "own products" on public.products
    for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

-- History rows are owned via their parent product.
drop policy if exists "own history" on public.price_history;
create policy "own history" on public.price_history
    for all
    using (exists (
        select 1 from public.products p
        where p.id = price_history.product_id and p.user_id = auth.uid()
    ))
    with check (exists (
        select 1 from public.products p
        where p.id = price_history.product_id and p.user_id = auth.uid()
    ));

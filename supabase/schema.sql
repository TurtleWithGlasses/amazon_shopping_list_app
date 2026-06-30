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
    image_url       text,
    last_price      double precision,
    last_stock      text,
    prev_price      double precision,
    prev_stock      text,
    price_changed   boolean not null default false,
    stock_changed   boolean not null default false,
    position        integer not null default 0,
    created_at      timestamptz not null default now(),
    last_checked    timestamptz,
    target_price    double precision
);
create index if not exists products_user_idx on public.products (user_id);

-- Migration for existing projects: add the manual-ordering column if missing.
alter table public.products add column if not exists position integer not null default 0;
-- Product thumbnail URL (Phase 13).
alter table public.products add column if not exists image_url text;
-- Target-price alert threshold (Phase 33).
alter table public.products add column if not exists target_price double precision;

create table if not exists public.price_history (
    id            bigint generated always as identity primary key,
    product_id    bigint not null references public.products (id) on delete cascade,
    price         double precision,
    stock         text,
    captured_at   timestamptz not null default now()
);
create index if not exists price_history_product_idx
    on public.price_history (product_id, captured_at);

-- Product groups / comparison sets (Phase 34).
create table if not exists public.groups (
    id          bigint generated always as identity primary key,
    user_id     uuid not null references auth.users (id) on delete cascade,
    name        text not null,
    created_at  timestamptz not null default now()
);
create index if not exists groups_user_idx on public.groups (user_id);

create table if not exists public.group_members (
    id          bigint generated always as identity primary key,
    group_id    bigint not null references public.groups (id) on delete cascade,
    product_id  bigint not null references public.products (id) on delete cascade,
    unique (group_id, product_id)
);
create index if not exists group_members_group_idx on public.group_members (group_id);

-- Shopping cart items (Phase 38). A product appears at most once per user; the
-- quantity carries the count. References a tracked product, so price changes
-- flow through to the cart total automatically.
create table if not exists public.cart_items (
    id          bigint generated always as identity primary key,
    user_id     uuid not null references auth.users (id) on delete cascade,
    product_id  bigint not null references public.products (id) on delete cascade,
    quantity    integer not null default 1,
    unique (user_id, product_id)
);
create index if not exists cart_items_user_idx on public.cart_items (user_id);

-- ── Row-level security ──────────────────────────────────────────────────────
alter table public.products enable row level security;
alter table public.price_history enable row level security;
alter table public.groups enable row level security;
alter table public.group_members enable row level security;
alter table public.cart_items enable row level security;

-- Users can only touch their own groups.
drop policy if exists "own groups" on public.groups;
create policy "own groups" on public.groups
    for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

-- Group membership is owned via the parent group.
drop policy if exists "own group_members" on public.group_members;
create policy "own group_members" on public.group_members
    for all
    using (exists (
        select 1 from public.groups g
        where g.id = group_members.group_id and g.user_id = auth.uid()
    ))
    with check (exists (
        select 1 from public.groups g
        where g.id = group_members.group_id and g.user_id = auth.uid()
    ));

-- Users can only touch their own cart items.
drop policy if exists "own cart_items" on public.cart_items;
create policy "own cart_items" on public.cart_items
    for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

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

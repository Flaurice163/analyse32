create table if not exists public.ventes_workspace (
    user_id uuid primary key references auth.users (id) on delete cascade,
    ventes_journalieres jsonb not null default '[]'::jsonb
        check (jsonb_typeof(ventes_journalieres) = 'array'),
    ventes_produits jsonb not null default '[]'::jsonb
        check (jsonb_typeof(ventes_produits) = 'array'),
    catalogue_produits jsonb not null default '[]'::jsonb
        check (jsonb_typeof(catalogue_produits) = 'array'),
    objectifs jsonb not null default '[]'::jsonb
        check (jsonb_typeof(objectifs) = 'array'),
    magasins jsonb not null default '[]'::jsonb
        check (jsonb_typeof(magasins) = 'array'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.ventes_workspace
    add column if not exists magasins jsonb not null default '[]'::jsonb;

alter table public.ventes_workspace enable row level security;

drop policy if exists "Users manage their own sales workspace"
    on public.ventes_workspace;
create policy "Users manage their own sales workspace"
    on public.ventes_workspace
    for all
    to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

grant select, insert, update, delete
    on public.ventes_workspace
    to authenticated;

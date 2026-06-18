# Supabase setup (Phase 6 — accounts + cloud sync)

Do these steps once, then paste your two keys back to me.

## 1. Create a free project
1. Go to <https://supabase.com> → sign in → **New project**.
2. Pick a name, a strong database password (you won't need it for the app), and a region close to you.
3. Wait ~1 minute for it to provision.

## 2. Create the tables
1. In the project, open **SQL Editor** → **New query**.
2. Paste the contents of [supabase/schema.sql](supabase/schema.sql) and click **Run**.
3. You should see "Success". This creates `products` + `price_history` with row-level security so each user only sees their own rows.

## 3. Confirm email is enabled (it is by default)
1. **Authentication → Providers → Email** — make sure **Confirm email** is ON.
2. New users will get a confirmation link by email; they click it, then log in.
   - The free tier's built-in mailer is rate-limited and fine for testing. (Later you can plug in a real SMTP provider for production volume.)

## 4. Grab your keys
1. **Project Settings → API**.
2. Copy:
   - **Project URL** (looks like `https://abcd1234.supabase.co`)
   - **anon public** key (a long JWT under "Project API keys")
   > Do **NOT** share the `service_role` key — it bypasses security.

## 5. Give them to the app
Create a file named `config.local.json` in the project root (it's git-ignored), based on
[config.example.json](config.example.json):

```json
{
  "supabase_url": "https://abcd1234.supabase.co",
  "supabase_anon_key": "eyJhbGciOi..."
}
```

Then paste the same two values here in chat so I can wire up and test auth + sync.

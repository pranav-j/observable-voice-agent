# 0008: Limits for a public demo

- **Status:** accepted
- **Date:** 2026-10-12

## Context

A public demo URL lets anyone start a call, and every call costs money: the LLM always, and speech too when hosted speech is on. It also ties up the worker's CPU when local speech is on. Without limits, one person reloading the page, or a script, could run up the bill or keep everyone else out.

Three things bound what the demo can cost: how long a call lasts, how many calls one person can start, and how many calls happen in a day.

## Decision

- **Call length:** `MAX_CALL_SECONDS` (default 300). The worker ends the call when it runs out, and `IDLE_TIMEOUT_SECONDS` ends it sooner if the caller goes quiet. This already existed.
- **Calls per IP:** `CALLS_PER_IP_PER_HOUR`. `/token` refuses a new call from an address that has started that many calls in the last hour, with HTTP 429, a reason the web app shows, and `Retry-After`.
- **Calls per day:** `CALLS_PER_DAY`, across all callers, reset at midnight UTC. Together with the call length, it caps the day's call minutes at `CALLS_PER_DAY × MAX_CALL_SECONDS / 60`, and through the cost per minute in the eval reports, the day's spend.
- **Where the IP comes from:** the connection's address by default. With `TRUST_PROXY=true`, the last entry of `X-Forwarded-For`, which is the one the hosting proxy adds. Earlier entries come from the client and can be made up.
- **Defaults:** both limits are 0, meaning none, so local development and the eval harness aren't affected. A deployment sets them.
- **Counts are kept in memory** in the backend process.

## Alternatives

- **Counts in Postgres.** They would survive restarts and work across several backend instances. The demo runs one instance, and a restart that resets the counts at worst allows one extra day's worth of calls. Not worth a table and a migration yet.
- **A daily cap on spend instead of calls.** It's the number that actually matters, but the spend of a call is only known after it ends, and the worker writes it. Capping calls, with a cap on call length, bounds spend ahead of time using numbers already measured.
- **Limits in a reverse proxy or the hosting platform.** Platform rate limits vary by provider and don't know what a call is. Doing it in `/token`, the one place every call starts, works the same everywhere.
- **Sign-in or a CAPTCHA.** It stops scripts better, but it adds friction to a demo that should start with one click.

## Consequences

- Restarting the backend resets the counts.
- Running more than one backend instance would multiply the limits. That needs the Postgres version first.
- People behind one shared address, like an office network, share one hourly allowance.
- A caller who gets a token but never joins still uses up a call. The limits count started calls, not completed ones.

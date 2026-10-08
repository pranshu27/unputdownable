---
name: zoho-timesheet-backfill
description: Use when backfilling Zoho or DATAECONOMY weekly timesheets, cloning the previous week every Friday with Playwright, fixing INVALID_CSRF_TOKEN failures, replaying addWeekTimesheet requests from an authenticated browser session, or skipping holiday and max-hours blocked days.
---

# Zoho Timesheet Backfill Skill

Use this skill when a user needs Zoho weekly timesheets submitted, repaired, or automatically cloned from the previous week, and notebook or shell requests are failing because browser session state has expired.

## When to use

Use when the user asks things like:
- "Backfill my Zoho timesheet"
- "Start from 8 Feb"
- "Use the curl/request I sent"
- "Why am I getting INVALID_CSRF_TOKEN?"
- "Replay this addWeekTimesheet request"
- "Skip holidays and leaves"
- "Clone last week into this week"
- "Run this every Friday automatically"

## Core rule

Prefer Playwright against the authenticated browser session on `https://my.dataeconomy.ai` over notebook `requests`, `curl`, or hardcoded cookies.

Why:
- hardcoded `Cookie` headers go stale quickly
- `CSRF_TOKEN` must match the active browser session
- browser-managed session state can succeed even when copied notebook code fails
- Playwright can inspect the prior week and post the new week in one controlled flow

## Automation goal

The preferred automatic workflow is:

1. Open the signed-in `my.dataeconomy.ai` timelog page on Friday.
2. Read the current browser cookies and CSRF token from the page context.
3. Read or reconstruct the previous week's weekday entries.
4. Build the current week's `logParams` by cloning Monday through Friday from the previous week.
5. Submit the new week with `addWeekTimesheet` from the same browser context.
6. If Zoho rejects one weekday because of leave, holiday, or max-hours rules, resubmit the week with that day omitted.

This is the path that should be automated.

## Proven workflow

### 1. Verify the right browser origin

Open or reuse the signed-in `my.dataeconomy.ai` page, not only `peopleplus.zoho.in`.

Check the live cookie values from the page context:
- `CSRF_TOKEN`
- `iamcsr`
- `CT_CSRF_TOKEN`

Use `run_playwright_code` page evaluation to read `document.cookie` and extract the token values.

### 2. Prefer Playwright over notebook or shell replay

Do not start by hardcoding cookie headers into notebooks.

Use Playwright directly on the signed-in page and issue the request with:
- `fetch`
- `credentials: "include"`
- `URLSearchParams`

This keeps the request bound to the actual authenticated browser state.

### 3. Test one week first

Before a large backfill, submit a single `addWeekTimesheet` request for one week.

Use:
- `mode=addWeekTimesheet`
- `userErecNo`
- `conreqcsr=<live csrf token>`
- `fromDate`
- `toDate`
- `logParams=<JSON array>`

Submit it from the browser page with `fetch(..., { credentials: "include" })` and `URLSearchParams`.

If the single week succeeds, continue with the remaining weeks.

### 4. Clone the previous week on Friday

For weekly automation, derive the target week and source week from the current date.

Friday rule:
- if today is Friday, clone the immediately previous Sunday-to-Saturday week into the current Sunday-to-Saturday week

Weekday mapping rule:
- copy prior `day2` to current `day2`
- copy prior `day3` to current `day3`
- copy prior `day4` to current `day4`
- copy prior `day5` to current `day5`
- copy prior `day6` to current `day6`

Clone only weekday timelogs. Do not attempt to create weekend rows.

If the previous week cannot be fetched structurally from page APIs, reconstruct it from known task templates or from visible timelog data in the active page session.

### 5. Batch the remaining weeks

Use Sunday-aligned weekly ranges for Zoho week submission.

Example ranges:
- `2026-02-08` to `2026-02-14`
- `2026-02-15` to `2026-02-21`

Loop week by week and capture:
- `fromDate`
- `toDate`
- HTTP status
- response body

### 6. Handle business-rule failures

Common responses:

#### `INVALID_CSRF_TOKEN`

Meaning:
- notebook or shell request is using stale session values

Action:
- stop using hardcoded cookies
- read fresh cookie values from the live browser page
- retry from Playwright browser context

#### `TL_0011`

Meaning:
- cannot log time on weekend, holiday, or leave day

Action:
- resubmit the same week with the blocked day removed from `logParams`

#### `TL_0006`

Meaning:
- logged hours would exceed the maximum allowed for that day

Action:
- do not keep retrying the same payload
- either skip that day or inspect existing entries first

### 7. Only update notebook code after the browser path works

If the user wants notebook code saved, reflect the known-good approach afterward.

Important:
- do not claim the notebook path works just because the payload looks correct
- if browser submission works but notebook submission fails, say so explicitly

## Playwright pattern

The preferred pattern is to run the whole submission inside `run_playwright_code`.

```javascript
return await page.evaluate(async () => {
  const entries = Object.fromEntries(
    document.cookie
      .split(";")
      .map(part => part.trim())
      .filter(Boolean)
      .map(part => {
        const idx = part.indexOf("=")
        return [part.slice(0, idx), part.slice(idx + 1)]
      })
  )

  const csrf = entries.CSRF_TOKEN || entries.iamcsr || entries.CT_CSRF_TOKEN || ""

  const payload = new URLSearchParams({
    mode: "addWeekTimesheet",
    logParams: JSON.stringify(logParams),
    userErecNo,
    conreqcsr: csrf,
    fromDate,
    toDate
  })

  const response = await fetch("/737907319/timesheet.zp", {
    method: "POST",
    credentials: "include",
    headers: {
      "Accept": "*/*",
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
      "X-Requested-With": "XMLHttpRequest"
    },
    body: payload
  })

  return {
    status: response.status,
    text: await response.text()
  }
})
```

## Friday cloning pattern

Use this logic when the ask is "do it automatically every Friday":

1. Compute the current week's Sunday.
2. Compute the previous week's Sunday.
3. Build the current week date range from the current Sunday.
4. Reuse the previous week's weekday tasks and hours.
5. Submit once.
6. If Zoho returns `TL_0011` or `TL_0006`, remove the blocked day and resubmit.

Pseudo-logic:

```javascript
const weekdayKeys = ["day2", "day3", "day4", "day5", "day6"]

const clonedLogParams = previousWeekEntries
  .filter(entry => weekdayKeys.includes(entry.dayKey))
  .map(entry => ({
    [entry.dayKey]: entry.hours,
    jobId: entry.jobId,
    projectId: entry.projectId,
    taskName: entry.taskName,
    billStatus: entry.billStatus ?? "0"
  }))
```

## Scheduling guidance

This skill is Playwright-first, but fully automatic Friday execution still requires a signed-in browser context.

Practical constraints:
- if the browser session is expired, automation will fail until the user signs in again
- if MFA or SSO is enforced, a completely headless unattended flow may not stay valid long term

Recommended operating mode:
- keep the signed-in `my.dataeconomy.ai` page available in VS Code integrated browser when running the skill
- or use a scheduled environment that preserves the authenticated browser profile

If the user asks for true unattended execution, call out the session persistence requirement before promising it.

## Request pattern

The working submission shape is:

```javascript
const payload = new URLSearchParams({
  mode: "addWeekTimesheet",
  logParams: JSON.stringify([
    { day2: "08:00", jobId, projectId, taskName: "...", billStatus: "0" },
    { day3: "08:00", jobId, projectId, taskName: "...", billStatus: "0" },
    { day4: "08:00", jobId, projectId, taskName: "...", billStatus: "0" },
    { day5: "08:00", jobId, projectId, taskName: "...", billStatus: "0" },
    { day6: "08:00", jobId, projectId, taskName: "...", billStatus: "0" }
  ]),
  userErecNo,
  conreqcsr: csrf,
  fromDate,
  toDate
})

await fetch("/737907319/timesheet.zp", {
  method: "POST",
  credentials: "include",
  headers: {
    "Accept": "*/*",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest"
  },
  body: payload
})
```

## Execution checklist

1. Confirm the signed-in `my.dataeconomy.ai` page is available.
2. Read live CSRF values from browser cookies.
3. If this is Friday automation, compute source week and target week first.
4. Build cloned weekday `logParams` from the previous week.
5. Test one week.
6. Batch remaining weeks when needed.
7. Retry `TL_0011` weeks with blocked dates removed.
8. Stop and report any `TL_0006` max-hours conflicts.
9. Only then update notebook code if requested.

## Known good outcome

This workflow successfully backfilled weekly entries from `2026-02-08` onward using the live `my.dataeconomy.ai` browser session.

Weeks that required reduced payloads:
- `2026-03-01` to `2026-03-07` skipped `2026-03-03`
- `2026-03-15` to `2026-03-21` skipped `2026-03-19`
- `2026-04-26` to `2026-05-02` skipped `2026-05-01`

## Learnings

- `peopleplus.zoho.in` cookies are not enough when the actual successful origin is `my.dataeconomy.ai`.
- Matching `CSRF_TOKEN` strings in notebook code is still insufficient when broader browser session state is stale.
- One-week validation before bulk replay is the cheapest discriminating check.
- Playwright is the most reliable execution surface because it reuses the active authenticated browser state instead of imitating it.
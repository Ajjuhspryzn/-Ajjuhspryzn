# Setup (5 minutes, one-time)

## 1. Create the special profile repo
1. Create a new **public** repo named `<your-github-username>`.
2. Push everything in this folder to it.

## 2. Set two repo variables
**Settings → Secrets and variables → Actions → Variables tab:**

| Name | Value |
|---|---|
| `GH_USERNAME` | your GitHub username |
| `LEETCODE_USERNAME` | your LeetCode username |

## 3. Get a token for the contribution graph (recommended)
GitHub's GraphQL API requires auth even for public data.
1. GitHub → Settings → Developer settings → Personal access tokens →
   Tokens (classic) → Generate new token. No scopes needed.
2. Add it as a repo **secret** named `GH_STATS_TOKEN`.

Without this, everything else still works — only the contribution graph /
monthly quest bar shows 0.

## 4. Let Actions push commits
**Settings → Actions → General → Workflow permissions →
"Read and write permissions."**

## 5. Run it once
**Actions tab → "Update Solo Leveling Status" → Run workflow.**

## 6. (Optional) Real email alerts

Since notifications only otherwise show up when you visit your profile page,
you can have the Action email you the moment something new happens (level
up, quest arrival, warning, penalty, monthly goal, skill/title unlocked).

1. You need a Gmail account with an **App Password** (a regular Gmail
   password won't work for SMTP):
   - Turn on 2-Step Verification: myaccount.google.com/security
   - Then create an app password: myaccount.google.com/apppasswords
   - Name it anything (e.g. "github-alerts"), copy the 16-character code
2. Repo → **Settings → Secrets and variables → Actions → Secrets tab**:
   - `EMAIL_USERNAME` = your full Gmail address
   - `EMAIL_PASSWORD` = the 16-character app password (not your real password)
3. Optional — if you want alerts sent somewhere other than that same Gmail
   inbox, add a repo **variable** `EMAIL_TO` with the destination address.
   Otherwise it emails `EMAIL_USERNAME` by default.

That's it — no code changes needed, the workflow already has the step.
It only sends an email when `generate_card.py` detects something genuinely
new that run; identical hourly re-checks stay silent.

Not on Gmail? Any SMTP provider works — just change `server_address` /
`server_port` in `.github/workflows/update-status.yml`'s "Email alert" step
(e.g. Outlook: `smtp.office365.com:587`).

### `data/skills.json` — log a skill whenever you learn one
```json
["YOLOv11 Object Detection", "React + Tailwind"]
```
Fires `You have learned [Skill: X].` the next run.

### `data/config.json` — your goal + timezone
```json
{
  "monthly_contribution_goal": 150,
  "timezone_offset_hours": 5.5,
  "warning_hour_local": 21
}
```
- `monthly_contribution_goal` — hit this many real contributions
  (commits/PRs/issues/reviews) in a calendar month for a **permanent +500 XP**
  bonus, reliably triggering a level-up.
- `timezone_offset_hours` — defaults to **5.5 (IST)**. GitHub Actions runs in
  UTC, so this shifts "today" and "this month" to match your local calendar
  day instead of the UTC day. Change it if you're not in IST.
- `warning_hour_local` — local hour (0–23) after which an incomplete daily
  quest triggers the heart-stop warning. Default 21 = 9 PM local.

Everything else — level, job/class, titles, quests, notifications — is
100% automatic.

## 7. (Optional) Real native GitHub notifications — not email, not the README

This is different from step 6: instead of sending email, the Action creates
a single issue titled **"🔔 System Notifications"** in your repo and posts a
new comment on it every time something happens. Issue comments are one of
the few things GitHub itself turns into a **real notification** — the bell
icon on github.com, and an actual push notification on your phone if you
use the GitHub Mobile app.

Nothing to configure in the repo — it works out of the box using the
built-in `GITHUB_TOKEN`. What matters is your **personal GitHub notification
settings**, since that controls whether GitHub actually alerts you:

1. **github.com/settings/notifications** → under "Watching," make sure
   `Automatically watch repositories that I push to` is on (usually the
   default), and that "Issues" is checked wherever you want alerts
   (web / email / mobile).
2. For a phone push notification specifically: install the **GitHub Mobile
   app**, sign in, then in the app go to Settings → Notifications and turn
   push notifications on.
3. The first time the Action runs, open the "🔔 System Notifications" issue
   on your repo once and confirm you're subscribed (there's a "Subscribe"
   button in the sidebar if you're not already).

You can use email (step 6), this (step 7), both, or neither — they're
independent.

---

## How the daily quest lifecycle works

Each local day:
1. **Arrival** — first check of a new local day posts
   `[Daily Quest] A new quest has arrived.`
2. **Warning** — if it's past `warning_hour_local` and you haven't both
   pushed a commit *and* solved a LeetCode problem yet, you get one warning:
   `WARNING: Your heart will stop if you fail to complete today's Daily
   Quest in time.` (Fires once per day, not every hourly run.)
3. **Penalty** — if the day ends with the quest still incomplete, the next
   run posts `[Penalty] ... The Player possesses a Black Heart.` and assigns
   a tougher quest: *"PENALTY: Solve 2 LeetCode problems today."* Clear it
   the same way (by actually solving 2) and you get
   `The Black Heart has been cleansed.` It also just expires after one day
   either way, so it never permanently stacks.

One honest limitation: push-day detection uses UTC dates from GitHub's
public events API (full timestamps aren't easy to re-bucket cheaply), while
the arrival/warning/penalty *timing* uses your local offset. Near midnight
these can disagree by a few hours — not exact, but close enough for a daily
habit tracker.

## The visitor greeting

`assets/greeting.svg` renders "Do you really want to become a Player?" with
YES/NO buttons, embedded at the top of the README. **This is the same for
every visitor** — GitHub has no API or mechanism for a static README to
detect who's viewing it or whether they're logged in, so true per-visitor
personalization isn't possible here. Both buttons currently scroll to the
projects section; point them at different anchors/links if you'd like.

## How leveling works (recap)
Total XP = LeetCode solves (weighted) + web repos + AI/ML repos + total
repos + followers/stars + skills learned + yearly contributions + push
streak + banked monthly-goal bonuses. Job = Hunter rank (tied to level) +
class (tied to your strongest category: DSA→Necromancer, Web Dev→Assassin,
AI/ML→Mage, Projects→Architect, Community→Paladin, Skills→Sage). Level 100
evolves everyone into **Shadow Monarch**, matching the anime's job-change
scene, with `Your job has evolved: [X] -> [Shadow Monarch].`

`data/state.json` is the system's memory — auto-managed, don't hand-edit it.

## Known limitations
- Contribution graph (and therefore private-repo detection) needs a token
  (step 3) — without one, commit detection falls back to public-repo pushes
  only. With the token, it also needs "Include private contributions" turned
  on in your GitHub profile settings, or private activity won't count there
  either — it's a GitHub-side setting, not something this script controls.
- LeetCode's API is public but unofficial; if it changes, that stat
  degrades to 0 rather than breaking the whole Action.
- Repo bucketing (AI/ML vs Web Dev) is keyword-based on topics/name/
  description — tag repos with GitHub **topics** for best accuracy.
- Runs hourly + on push to this repo, so there's up to ~1 hour of lag
  between actually completing a quest and the card reflecting it — not
  instant, but automatic.
- LeetCode "solved today" is a total-count diff (today's total vs. a
  snapshot from the start of the day), not a true per-submission timestamp
  check — accurate for "did the count go up," not for exactly which
  problem or when.

#!/usr/bin/env python3
"""
Solo Leveling GitHub Status System — v3
------------------------------------------
Automatic: GitHub repos/activity, GitHub contribution graph, LeetCode solves.
Manual (tiny, on purpose): data/skills.json (skills you've learned) and
data/config.json (your monthly contribution goal).

Renders:
    assets/status-card.svg    -> STATUS window (level, class, title, stats, monthly quest)
    assets/quest-card.svg     -> auto-detected DAILY QUEST tracker
    assets/notification.svg   -> latest auto-generated NOTIFICATION

Run locally:
    GITHUB_USERNAME=you LEETCODE_USERNAME=you GH_STATS_TOKEN=ghp_xxx python3 scripts/generate_card.py

GH_STATS_TOKEN (or GITHUB_TOKEN in Actions) is required for the contribution
graph, since that's a GraphQL query and GitHub's GraphQL API requires auth
even for public data. Everything else works without it.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(ROOT, "data", "state.json")
SKILLS_PATH = os.path.join(ROOT, "data", "skills.json")
CONFIG_PATH = os.path.join(ROOT, "data", "config.json")
ASSETS_DIR = os.path.join(ROOT, "assets")

GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "").strip()
LEETCODE_USERNAME = os.environ.get("LEETCODE_USERNAME", "").strip()
GITHUB_TOKEN = os.environ.get("GH_STATS_TOKEN") or os.environ.get("GITHUB_TOKEN", "")

AI_ML_KEYWORDS = {"ai", "ml", "machine-learning", "deep-learning", "computer-vision",
                   "yolo", "yolov5", "yolov11", "pytorch", "tensorflow", "cnn", "nlp",
                   "data-science", "artificial-intelligence", "posenet"}
WEB_KEYWORDS = {"web", "webapp", "website", "react", "nextjs", "frontend", "html",
                 "css", "javascript", "typescript", "vue", "node", "express", "flask",
                 "django"}

# level -> hunter rank
RANK_TITLES = [
    (0, "E-Rank Hunter"), (10, "D-Rank Hunter"), (20, "C-Rank Hunter"),
    (30, "B-Rank Hunter"), (40, "A-Rank Hunter"), (55, "S-Rank Hunter"),
    (70, "National Level Hunter"),
]
SHADOW_MONARCH_LEVEL = 100  # full class evolution, overrides specialization entirely

# dominant stat category -> RPG class (your "base job," like the anime's starting class)
CLASSES = {
    "DSA": "Necromancer",       # commands an army of solved problems
    "WEB DEV": "Assassin",
    "AI / ML": "Mage",
    "PROJECTS": "Architect",
    "COMMUNITY": "Paladin",
    "SKILLS": "Sage",
}

MONTHLY_BONUS_XP = 500


def sys_msg(body):
    """Standard notification voice — every notification in the system
    reads as a directive/statement from The System, e.g.
    'The System wants you to know you have reached Level 4.'"""
    return f"The System wants you to {body}"

# achievement key -> (condition over ctx, display label)
def _achievement_checks(ctx):
    gh, lc, stats = ctx["gh"], ctx["lc"], ctx["stats"]
    return [
        ("first_push", gh["public_repos"] > 0 or len(gh["recent_push_days"]) > 0, "Awakened"),
        ("streak_7", stats["streak"] >= 7, "Consistent Grinder"),
        ("streak_30", stats["streak"] >= 30, "Iron Will"),
        ("lc_50", lc["total"] >= 50, "Problem Solver"),
        ("lc_200", lc["total"] >= 200, "Algorithm Slayer"),
        ("lc_500", lc["total"] >= 500, "Grandmaster of Grind"),
        ("repos_10", gh["public_repos"] >= 10, "Builder"),
        ("repos_25", gh["public_repos"] >= 25, "Prolific Architect"),
        ("stars_10", gh["total_stars"] >= 10, "Recognized"),
        ("stars_100", gh["total_stars"] >= 100, "Renowned"),
        ("ai_ml_5", gh["ai_ml_repos"] >= 5, "Neural Network Tamer"),
        ("web_5", gh["web_repos"] >= 5, "Pixel Pusher"),
    ]

TITLE_LABELS = {k: label for k, _cond, label in
                _achievement_checks({"gh": {"public_repos": 0, "recent_push_days": set(),
                                             "total_stars": 0, "ai_ml_repos": 0, "web_repos": 0},
                                      "lc": {"total": 0},
                                      "stats": {"streak": 0}})}


# --------------------------------------------------------------------------
# Data fetching
# --------------------------------------------------------------------------

def gh_headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "solo-leveling-github-status",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def fetch_github_stats(username):
    stats = {
        "followers": 0, "public_repos": 0, "total_stars": 0,
        "ai_ml_repos": 0, "web_repos": 0, "other_repos": 0,
        "recent_push_days": set(), "top_languages": {},
    }
    if not username:
        return stats

    try:
        r = requests.get(f"https://api.github.com/users/{username}",
                          headers=gh_headers(), timeout=15)
        r.raise_for_status()
        user = r.json()
        stats["followers"] = user.get("followers", 0)
        stats["public_repos"] = user.get("public_repos", 0)
    except requests.RequestException as e:
        print(f"[warn] github user fetch failed: {e}", file=sys.stderr)
        return stats

    try:
        repos, page = [], 1
        while True:
            r = requests.get(
                f"https://api.github.com/users/{username}/repos",
                params={"per_page": 100, "page": page, "type": "owner"},
                headers=gh_headers(), timeout=15)
            r.raise_for_status()
            batch = r.json()
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1

        for repo in repos:
            stats["total_stars"] += repo.get("stargazers_count", 0)
            lang = repo.get("language")
            if lang:
                stats["top_languages"][lang] = stats["top_languages"].get(lang, 0) + 1

            topics = set(t.lower() for t in repo.get("topics", []))
            name = (repo.get("name") or "").lower()
            desc = (repo.get("description") or "").lower()
            haystack = topics | set(name.split("-")) | set(desc.split())

            if haystack & AI_ML_KEYWORDS:
                stats["ai_ml_repos"] += 1
            elif haystack & WEB_KEYWORDS:
                stats["web_repos"] += 1
            else:
                stats["other_repos"] += 1
    except requests.RequestException as e:
        print(f"[warn] github repos fetch failed: {e}", file=sys.stderr)

    try:
        r = requests.get(
            f"https://api.github.com/users/{username}/events/public",
            params={"per_page": 100}, headers=gh_headers(), timeout=15)
        r.raise_for_status()
        for event in r.json():
            if event.get("type") == "PushEvent":
                day = event.get("created_at", "")[:10]
                if day:
                    stats["recent_push_days"].add(day)
    except requests.RequestException as e:
        print(f"[warn] github events fetch failed: {e}", file=sys.stderr)

    return stats


def fetch_contribution_calendar(username):
    """GitHub's real contribution graph (commits + PRs + issues + reviews).
    Requires an authenticated token (GraphQL always requires auth, even for
    public data) — falls back to zeros if no token is available."""
    result = {"total_year": 0, "this_month": 0, "by_day": {}}
    if not username or not GITHUB_TOKEN:
        return result

    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
    }
    """
    try:
        r = requests.post(
            "https://api.github.com/graphql",
            json={"query": query, "variables": {"login": username}},
            headers={**gh_headers(), "Content-Type": "application/json"},
            timeout=20,
        )
        r.raise_for_status()
        payload = r.json()
        calendar = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        result["total_year"] = calendar["totalContributions"]

        now = datetime.now(timezone.utc)
        month_prefix = now.strftime("%Y-%m")
        month_total = 0
        for week in calendar["weeks"]:
            for day in week["contributionDays"]:
                result["by_day"][day["date"]] = day["contributionCount"]
                if day["date"].startswith(month_prefix):
                    month_total += day["contributionCount"]
        result["this_month"] = month_total
    except (requests.RequestException, KeyError, TypeError, ValueError) as e:
        print(f"[warn] contribution calendar fetch failed: {e}", file=sys.stderr)

    return result


def fetch_leetcode_stats(username):
    stats = {"easy": 0, "medium": 0, "hard": 0, "total": 0, "ranking": None}
    if not username:
        return stats

    query = """
    query userProfile($username: String!) {
      matchedUser(username: $username) {
        submitStatsGlobal { acSubmissionNum { difficulty count } }
        profile { ranking }
      }
    }
    """
    try:
        r = requests.post(
            "https://leetcode.com/graphql",
            json={"query": query, "variables": {"username": username}},
            headers={"Content-Type": "application/json", "Referer": "https://leetcode.com"},
            timeout=15,
        )
        r.raise_for_status()
        matched = r.json()["data"]["matchedUser"]
        for row in matched["submitStatsGlobal"]["acSubmissionNum"]:
            diff = row["difficulty"].lower()
            if diff in ("easy", "medium", "hard"):
                stats[diff] = row["count"]
        stats["total"] = stats["easy"] + stats["medium"] + stats["hard"]
        stats["ranking"] = matched.get("profile", {}).get("ranking")
    except (requests.RequestException, KeyError, TypeError, ValueError) as e:
        print(f"[warn] leetcode fetch failed: {e}", file=sys.stderr)

    return stats


def load_skills():
    """data/skills.json — flat list of skill name strings. This is the one
    thing you hand-edit: add a line whenever you learn something new."""
    if not os.path.exists(SKILLS_PATH):
        return []
    with open(SKILLS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [s.strip() for s in data if isinstance(s, str) and s.strip()]


def load_config():
    defaults = {
        "monthly_contribution_goal": 150,
        # Hours to add to UTC so "today"/"this month" match your local calendar
        # day instead of GitHub's UTC day. IST = 5.5.
        "timezone_offset_hours": 5.5,
        # Local hour (0-23) after which an incomplete daily quest triggers
        # the heart-stop warning notification.
        "warning_hour_local": 21,
    }
    if not os.path.exists(CONFIG_PATH):
        return defaults
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    defaults.update(data)
    return defaults


def local_now(config):
    """Current time shifted to the user's local timezone (config-driven,
    since GitHub Actions always runs in UTC)."""
    offset = config.get("timezone_offset_hours", 0)
    return datetime.now(timezone.utc) + timedelta(hours=offset)


def load_state():
    defaults = {
        "last_level": 0, "last_job": "", "unlocked_titles": [],
        "known_skills": [], "notifications": [],
        "leetcode_baseline_today": 0, "last_run_date": "",
        "monthly_goals_claimed": [], "banked_xp": 0,
        "quest_tracking_date": "", "warned_today": False,
        "pending_penalty_quest": None,
    }
    if not os.path.exists(STATE_PATH):
        return defaults
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    defaults.update(data)
    return defaults


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# --------------------------------------------------------------------------
# Stat computation
# --------------------------------------------------------------------------

def compute_streak(push_days):
    if not push_days:
        return 0
    today = datetime.now(timezone.utc).date()
    day_set = set(datetime.strptime(d, "%Y-%m-%d").date() for d in push_days)
    cursor = today
    if cursor not in day_set:
        cursor -= timedelta(days=1)
    streak = 0
    while cursor in day_set:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def build_stats(gh, lc, contrib, skills, state):
    dsa = lc["easy"] * 1 + lc["medium"] * 2 + lc["hard"] * 4
    web_dev = gh["web_repos"] * 12
    ai_ml = gh["ai_ml_repos"] * 15
    projects = gh["public_repos"] * 5 + gh["other_repos"] * 2
    community = gh["followers"] * 3 + gh["total_stars"] * 2
    skills_xp = len(skills) * 40
    contrib_xp = contrib["total_year"] * 2
    streak = compute_streak(gh["recent_push_days"])

    live_xp = (dsa + web_dev + ai_ml + projects + community
               + skills_xp + contrib_xp + streak * 10)
    total_xp = live_xp + state.get("banked_xp", 0)  # banked = permanent monthly-goal bonuses

    level, xp_for_next, remaining_xp = 1, 250, total_xp
    while remaining_xp >= xp_for_next:
        remaining_xp -= xp_for_next
        level += 1
        xp_for_next = level * 250
    xp_pct = min(100, round((remaining_xp / xp_for_next) * 100)) if xp_for_next else 0

    stat_rows = [
        ("DSA", dsa, f"{lc['total']} solved"),
        ("WEB DEV", web_dev, f"{gh['web_repos']} repos"),
        ("AI / ML", ai_ml, f"{gh['ai_ml_repos']} repos"),
        ("PROJECTS", projects, f"{gh['public_repos']} total"),
        ("COMMUNITY", community, f"{gh['followers']} followers"),
        ("SKILLS", skills_xp, f"{len(skills)} learned"),
    ]
    dominant = max(stat_rows, key=lambda row: row[1])[0]

    return {
        "level": level, "xp_current": remaining_xp, "xp_needed": xp_for_next,
        "xp_pct": xp_pct, "streak": streak, "stat_rows": stat_rows,
        "dominant": dominant, "leetcode_ranking": lc.get("ranking"),
        "contrib_year": contrib["total_year"], "contrib_month": contrib["this_month"],
    }


def compute_job(level, dominant):
    rank = RANK_TITLES[0][1]
    for threshold, name in RANK_TITLES:
        if level >= threshold:
            rank = name
    if level >= SHADOW_MONARCH_LEVEL:
        return "Shadow Monarch"  # full evolution — class distinctions no longer apply
    cls = CLASSES.get(dominant, "Novice")
    return f"{rank} · {cls}"


def compute_quests(gh, lc, contrib, state, today_str):
    # Prefer the contribution graph (includes private repos, if you have
    # "Include private contributions" on in GitHub settings) — falls back to
    # the public-events check if no GH_STATS_TOKEN is configured.
    contrib_today = contrib.get("by_day", {}).get(today_str, 0)
    pushed_today = contrib_today > 0 or today_str in gh["recent_push_days"]

    baseline = state.get("leetcode_baseline_today", 0)
    if state.get("quest_tracking_date") != today_str:
        baseline = lc["total"]
    solved_today = lc["total"] > baseline

    quests = [
        {"name": "Push at least 1 commit today", "done": pushed_today},
        {"name": "Solve a new LeetCode problem today", "done": solved_today},
    ]
    return quests, baseline, pushed_today, solved_today


def apply_monthly_goal(contrib, config, state, month_key):
    """Grants a one-time, permanent XP bump the first time a calendar
    month's contribution goal is hit. Returns (banked_xp, claimed_list, notif_or_None)."""
    goal = config.get("monthly_contribution_goal", 150)
    claimed = list(state.get("monthly_goals_claimed", []))
    banked = state.get("banked_xp", 0)
    notif = None

    if contrib["this_month"] >= goal and month_key not in claimed:
        claimed.append(month_key)
        banked += MONTHLY_BONUS_XP
        notif = {"text": sys_msg(f"know the Monthly Quest is cleared: "
                                  f"{contrib['this_month']}/{goal} contributions — "
                                  f"+{MONTHLY_BONUS_XP} XP awarded.")}

    return banked, claimed, notif


PENALTY_QUEST_TARGET = 2  # extra LeetCode problems required to clear a Black Heart


def evaluate_quest_lifecycle(gh, lc, contrib, pushed_today, solved_today, state, config, local_dt, today_str):
    """Handles three things per your request:
    1. A '[Daily Quest] has arrived.' notification once per local day.
    2. A heart-stop WARNING if the quest is still incomplete after
       config['warning_hour_local'].
    3. On rollover to a new day, if YESTERDAY's quest wasn't fully done:
       a '[Player possesses a Black Heart]' penalty notification plus a new,
       tougher quest assigned as the penalty.
    Returns (notifications, updates_dict_for_state, penalty_quest_or_None).
    """
    notifications = []
    tracking_date = state.get("quest_tracking_date", "")
    pending_penalty = state.get("pending_penalty_quest")
    warned_today = state.get("warned_today", False)

    if tracking_date != today_str:
        # Rolled over into a new local day.
        if tracking_date:  # skip the failure check on the very first-ever run
            prev_pushed = (contrib.get("by_day", {}).get(tracking_date, 0) > 0
                           or tracking_date in gh["recent_push_days"])
            prev_baseline = state.get("leetcode_baseline_today", 0)
            prev_solved = lc["total"] > prev_baseline
            if not (prev_pushed and prev_solved):
                notifications.append({
                    "text": sys_msg("know that yesterday's Daily Quest was not completed. "
                                     "The Player now possesses a Black Heart.")
                })
                pending_penalty = {
                    "name": f"PENALTY: Solve {PENALTY_QUEST_TARGET} LeetCode problems today",
                    "target": PENALTY_QUEST_TARGET,
                    "assigned_date": today_str,
                    "penalty": True,
                }
            elif pending_penalty:
                # They cleared yesterday cleanly — let the old penalty lapse too.
                pending_penalty = None

        notifications.append({"text": sys_msg("complete today's Daily Quest.")})
        warned_today = False

    elif (not warned_today
          and local_dt.hour >= config.get("warning_hour_local", 21)
          and not (pushed_today and solved_today)):
        notifications.append({
            "text": sys_msg("finish today's Daily Quest before time runs out — "
                              "your heart will stop.")
        })
        warned_today = True

    # Check whether an active penalty quest has just been cleared.
    if pending_penalty and pending_penalty.get("assigned_date") == today_str:
        baseline = state.get("leetcode_baseline_today", 0)
        solved_extra = lc["total"] - baseline
        if solved_extra >= pending_penalty.get("target", PENALTY_QUEST_TARGET):
            notifications.append({"text": sys_msg("know the Black Heart has been cleansed.")})
            pending_penalty = None
    elif pending_penalty and pending_penalty.get("assigned_date") != today_str:
        pending_penalty = None  # penalty quests expire after one day either way

    updates = {
        "quest_tracking_date": today_str,
        "warned_today": warned_today,
        "pending_penalty_quest": pending_penalty,
    }
    return notifications, updates, pending_penalty


def update_notifications(gh, lc, skills, stats, job, state):
    notifications = list(state.get("notifications", []))
    unlocked = list(state.get("unlocked_titles", []))
    known_skills = list(state.get("known_skills", []))

    if stats["level"] > state.get("last_level", 0):
        notifications.append({"text": sys_msg(f"know you have reached Level {stats['level']}.")})

    prev_job = state.get("last_job", "")
    if job != prev_job and prev_job:
        notifications.append({"text": sys_msg(f"know your job has evolved: [{prev_job}] -> [{job}].")})

    for skill in skills:
        if skill not in known_skills:
            known_skills.append(skill)
            notifications.append({"text": sys_msg(f"know a new skill has been recorded: [Skill: {skill}].")})

    ctx = {"gh": gh, "lc": lc, "stats": stats}
    for key, condition, label in _achievement_checks(ctx):
        if condition and key not in unlocked:
            unlocked.append(key)
            notifications.append({"text": sys_msg(f"know a new title has been granted: [Title: {label}].")})

    return notifications, unlocked, known_skills


# --------------------------------------------------------------------------
# SVG rendering
# --------------------------------------------------------------------------

PALETTE = {
    "bg": "#050912", "border": "#3fd4ff", "border_dim": "#1c4a63",
    "text": "#eaf6ff", "text_dim": "#6f9bb5", "accent": "#3fd4ff",
    "accent_green": "#39ff8c", "accent_gold": "#ffd257", "accent_purple": "#b98bff",
}
FONT = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"


def _defs():
    return f"""
    <defs>
      <linearGradient id="bgGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#0b1830"/>
        <stop offset="100%" stop-color="{PALETTE['bg']}"/>
      </linearGradient>
      <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur stdDeviation="2.2" result="blur"/>
        <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
    </defs>"""


def _corner_brackets(x, y, w, h, size=14, color=None):
    color = color or PALETTE["border"]
    corners = [(x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)]
    return "\n".join(
        f'<path d="M{cx} {cy + size*sy} L{cx} {cy} L{cx + size*sx} {cy}" '
        f'stroke="{color}" stroke-width="1.6" fill="none" filter="url(#glow)"/>'
        for cx, cy, sx, sy in corners
    )


def _bar(x, y, w, h, pct, fg, bg=None):
    bg = bg or PALETTE["border_dim"]
    pct = max(0, min(100, pct))
    fill_w = w * pct / 100
    return f"""
    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h/2}" fill="{bg}"/>
    <rect x="{x}" y="{y}" width="{fill_w}" height="{h}" rx="{h/2}" fill="{fg}" filter="url(#glow)"/>"""


def render_status_svg(stats, job, unlocked_titles, monthly_goal, gh_username):
    W, H = 560, 620
    titles = [TITLE_LABELS.get(k, k) for k in unlocked_titles] or ["Unranked"]
    title_line = titles[-1] + (f"  (+{len(titles)-1} more)" if len(titles) > 1 else "")

    rows_svg = []
    row_y = 372
    for i, (label, value, sub) in enumerate(stats["stat_rows"]):
        col, row = i % 2, i // 2
        rx = 48 if col == 0 else 300
        ry = row_y + row * 46
        rows_svg.append(f"""
        <text x="{rx}" y="{ry}" font-family="{FONT}" font-size="13" font-weight="700"
              letter-spacing="1.5" fill="{PALETTE['text_dim']}">{label}</text>
        <text x="{rx}" y="{ry+22}" font-family="{FONT}" font-size="21" font-weight="800"
              fill="{PALETTE['text']}">{value}
          <tspan font-size="12" font-weight="600" fill="{PALETTE['accent_green']}" dx="8">{sub}</tspan>
        </text>""")

    monthly_pct = min(100, round(stats["contrib_month"] * 100 / monthly_goal)) if monthly_goal else 0

    return f"""<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">
    {_defs()}
    <rect width="{W}" height="{H}" rx="10" fill="url(#bgGrad)" stroke="{PALETTE['border_dim']}"/>
    {_corner_brackets(10, 10, W-20, H-20)}

    <rect x="{W/2-90}" y="34" width="180" height="34" fill="none"
          stroke="{PALETTE['border']}" stroke-width="1.2" filter="url(#glow)"/>
    <text x="{W/2}" y="57" text-anchor="middle" font-family="{FONT}" font-size="18"
          font-weight="800" letter-spacing="6" fill="{PALETTE['text']}">STATUS</text>

    <text x="48" y="120" font-family="{FONT}" font-size="52" font-weight="800"
          fill="{PALETTE['accent']}" filter="url(#glow)">{stats['level']}</text>
    <text x="48" y="140" font-family="{FONT}" font-size="12" letter-spacing="2"
          fill="{PALETTE['text_dim']}">LEVEL</text>

    <text x="210" y="100" font-family="{FONT}" font-size="12" letter-spacing="1"
          fill="{PALETTE['text_dim']}">JOB: <tspan fill="{PALETTE['accent_purple']}" font-weight="700">{job}</tspan></text>
    <text x="210" y="122" font-family="{FONT}" font-size="12" letter-spacing="1"
          fill="{PALETTE['text_dim']}">TITLE: <tspan fill="{PALETTE['accent_gold']}" font-weight="700">{title_line}</tspan></text>
    <text x="210" y="144" font-family="{FONT}" font-size="11" letter-spacing="1"
          fill="{PALETTE['text_dim']}">HUNTER: <tspan fill="{PALETTE['text']}">@{gh_username or '—'}</tspan></text>

    <line x1="36" y1="172" x2="{W-36}" y2="172" stroke="{PALETTE['border_dim']}" stroke-width="1"/>

    <text x="48" y="200" font-family="{FONT}" font-size="11" font-weight="700" letter-spacing="1.5"
          fill="{PALETTE['text_dim']}">XP  {stats['xp_current']} / {stats['xp_needed']}</text>
    {_bar(48, 208, W-96, 10, stats['xp_pct'], PALETTE['accent'])}

    <text x="48" y="244" font-family="{FONT}" font-size="11" font-weight="700" letter-spacing="1.5"
          fill="{PALETTE['text_dim']}">STREAK  {stats['streak']} days</text>
    {_bar(48, 252, W-96, 10, min(100, stats['streak']*100/30), PALETTE['accent_green'])}

    <text x="48" y="288" font-family="{FONT}" font-size="11" font-weight="700" letter-spacing="1.5"
          fill="{PALETTE['text_dim']}">MONTHLY QUEST  {stats['contrib_month']} / {monthly_goal} contributions</text>
    {_bar(48, 296, W-96, 10, monthly_pct, PALETTE['accent_gold'])}

    <line x1="36" y1="332" x2="{W-36}" y2="332" stroke="{PALETTE['border_dim']}" stroke-width="1"/>
    <text x="{W/2}" y="350" text-anchor="middle" font-size="10" fill="{PALETTE['border_dim']}">&#9670;</text>

    {''.join(rows_svg)}

    <line x1="36" y1="{H-56}" x2="{W-36}" y2="{H-56}" stroke="{PALETTE['border_dim']}" stroke-width="1"/>
    <text x="48" y="{H-30}" font-family="{FONT}" font-size="11" letter-spacing="1"
          fill="{PALETTE['text_dim']}">TITLES: <tspan fill="{PALETTE['accent_gold']}" font-weight="700">{len(unlocked_titles)}</tspan>
      &#160;&#160;CONTRIB (YR): <tspan fill="{PALETTE['accent_gold']}" font-weight="700">{stats['contrib_year']}</tspan></text>
    <text x="{W-48}" y="{H-30}" text-anchor="end" font-family="{FONT}" font-size="10"
          fill="{PALETTE['text_dim']}">updated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</text>
    </svg>"""


def render_quest_svg(quests):
    W = 420
    H = 90 + 34 * len(quests) + 60
    rows = []
    for i, q in enumerate(quests):
        y = 96 + i * 34
        done = q.get("done", False)
        is_penalty = q.get("penalty", False)
        box_color = PALETTE["accent_green"] if done else (
            "#ff5d6c" if is_penalty else PALETTE["border_dim"])
        check = (f'<path d="M0 4 L3 8 L9 0" stroke="{PALETTE["accent_green"]}" '
                  'stroke-width="2" fill="none"/>') if done else ""
        text_color = PALETTE["text_dim"] if done else ("#ff5d6c" if is_penalty else PALETTE["text"])
        rows.append(f"""
        <rect x="40" y="{y-13}" width="16" height="16" rx="2" fill="none" stroke="{box_color}" stroke-width="1.4"/>
        <g transform="translate(43,{y-9})">{check}</g>
        <text x="68" y="{y}" font-family="{FONT}" font-size="14" fill="{text_color}"
              text-decoration="{'line-through' if done else 'none'}">{q.get('name','')}</text>""")

    return f"""<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">
    {_defs()}
    <rect width="{W}" height="{H}" rx="10" fill="url(#bgGrad)" stroke="{PALETTE['border_dim']}"/>
    {_corner_brackets(10, 10, W-20, H-20)}
    <text x="{W/2}" y="42" text-anchor="middle" font-family="{FONT}" font-size="12"
          letter-spacing="4" fill="{PALETTE['text_dim']}">DAILY QUEST</text>
    <text x="{W/2}" y="64" text-anchor="middle" font-family="{FONT}" font-size="15" font-weight="800"
          letter-spacing="1" fill="{PALETTE['text']}">Stay Awakened.</text>
    <line x1="30" y1="76" x2="{W-30}" y2="76" stroke="{PALETTE['border_dim']}"/>
    {''.join(rows)}
    <text x="{W/2}" y="{H-24}" text-anchor="middle" font-family="{FONT}" font-size="10"
          fill="#ff5d6c">WARNING: skipping days breaks your streak bonus.</text>
    </svg>"""


def _wrap_text(text, max_chars=34):
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def render_notification_svg(notifications):
    latest = notifications[-1] if notifications else {"text": sys_msg("push something. The System is watching.")}
    lines = _wrap_text(latest.get("text", ""))
    W = 420
    H = 110 + max(1, len(lines)) * 26 + 20

    line_svg = []
    start_y = 95
    for i, line in enumerate(lines):
        line_svg.append(
            f'<text x="{W/2}" y="{start_y + i*26}" text-anchor="middle" font-family="{FONT}" '
            f'font-size="15" font-weight="700" fill="{PALETTE["accent_gold"]}" '
            f'filter="url(#glow)">{line}</text>'
        )

    return f"""<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">
    {_defs()}
    <rect width="{W}" height="{H}" rx="10" fill="url(#bgGrad)" stroke="{PALETTE['border_dim']}"/>
    {_corner_brackets(10, 10, W-20, H-20)}
    <text x="30" y="42" font-family="{FONT}" font-size="14" font-weight="800" letter-spacing="3"
          fill="{PALETTE['text']}">NOTIFICATION</text>
    <line x1="30" y1="54" x2="{W-30}" y2="54" stroke="{PALETTE['border_dim']}"/>
    {''.join(line_svg)}
    </svg>"""


def render_greeting_svg():
    """Static 'will you accept this job?' banner shown to every visitor —
    GitHub gives no way to detect who's viewing a README, so this can't be
    personalized per-person, only styled like the system prompt."""
    W, H = 560, 220
    return f"""<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">
    {_defs()}
    <rect width="{W}" height="{H}" rx="10" fill="url(#bgGrad)" stroke="{PALETTE['border_dim']}"/>
    {_corner_brackets(10, 10, W-20, H-20)}
    <text x="{W/2}" y="46" text-anchor="middle" font-family="{FONT}" font-size="12"
          letter-spacing="4" fill="{PALETTE['text_dim']}">SYSTEM</text>
    <text x="{W/2}" y="92" text-anchor="middle" font-family="{FONT}" font-size="21"
          font-weight="800" fill="{PALETTE['text']}" filter="url(#glow)">Do you really want to become a Player?</text>

    <rect x="{W/2-140}" y="130" width="120" height="46" rx="4" fill="none"
          stroke="{PALETTE['accent_green']}" stroke-width="1.4" filter="url(#glow)"/>
    <text x="{W/2-80}" y="159" text-anchor="middle" font-family="{FONT}" font-size="15"
          font-weight="800" letter-spacing="2" fill="{PALETTE['accent_green']}">YES</text>

    <rect x="{W/2+20}" y="130" width="120" height="46" rx="4" fill="none"
          stroke="#ff5d6c" stroke-width="1.4" filter="url(#glow)"/>
    <text x="{W/2+80}" y="159" text-anchor="middle" font-family="{FONT}" font-size="15"
          font-weight="800" letter-spacing="2" fill="#ff5d6c">NO</text>
    </svg>"""


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    os.makedirs(ASSETS_DIR, exist_ok=True)

    gh = fetch_github_stats(GITHUB_USERNAME)
    lc = fetch_leetcode_stats(LEETCODE_USERNAME)
    contrib = fetch_contribution_calendar(GITHUB_USERNAME)
    skills = load_skills()
    config = load_config()
    state = load_state()

    ldt = local_now(config)
    today_str = ldt.strftime("%Y-%m-%d")
    month_str = ldt.strftime("%Y-%m")

    prior_notifications = list(state.get("notifications", []))

    banked_xp, claimed, monthly_notif = apply_monthly_goal(contrib, config, state, month_str)
    state["banked_xp"] = banked_xp
    state["monthly_goals_claimed"] = claimed

    stats = build_stats(gh, lc, contrib, skills, state)
    job = compute_job(stats["level"], stats["dominant"])
    quests, baseline, pushed_today, solved_today = compute_quests(gh, lc, contrib, state, today_str)

    lifecycle_notifs, lifecycle_updates, pending_penalty = evaluate_quest_lifecycle(
        gh, lc, contrib, pushed_today, solved_today, state, config, ldt, today_str)
    state.update(lifecycle_updates)

    if pending_penalty:
        penalty_baseline = state.get("leetcode_baseline_today", 0)
        penalty_done = (lc["total"] - penalty_baseline) >= pending_penalty.get("target", PENALTY_QUEST_TARGET)
        quests.append({"name": pending_penalty["name"], "done": penalty_done, "penalty": True})

    notifications, unlocked, known_skills = update_notifications(gh, lc, skills, stats, job, state)
    notifications.extend(lifecycle_notifs)
    if monthly_notif:
        notifications.append(monthly_notif)

    # Everything appended after the point where we started == genuinely new
    # this run. This is what (optionally) gets emailed — never re-sends
    # yesterday's notifications just because the card re-renders hourly.
    new_notifications = notifications[len(prior_notifications):]
    notifications = notifications[-8:]

    state.update({
        "last_level": stats["level"], "last_job": job,
        "unlocked_titles": unlocked, "known_skills": known_skills,
        "notifications": notifications,
        "leetcode_baseline_today": baseline, "last_run_date": today_str,
    })
    save_state(state)

    with open(os.path.join(ASSETS_DIR, "status-card.svg"), "w", encoding="utf-8") as f:
        f.write(render_status_svg(stats, job, unlocked, config["monthly_contribution_goal"], GITHUB_USERNAME))
    with open(os.path.join(ASSETS_DIR, "quest-card.svg"), "w", encoding="utf-8") as f:
        f.write(render_quest_svg(quests))
    with open(os.path.join(ASSETS_DIR, "notification.svg"), "w", encoding="utf-8") as f:
        f.write(render_notification_svg(notifications))
    with open(os.path.join(ASSETS_DIR, "greeting.svg"), "w", encoding="utf-8") as f:
        f.write(render_greeting_svg())

    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"has_new={'true' if new_notifications else 'false'}\n")
            body = "\n".join(f"- {n['text']}" for n in new_notifications)
            f.write(f"notif_body<<SOLO_LVL_EOF\n{body}\nSOLO_LVL_EOF\n")

    print(f"Level {stats['level']} | Job: {job} | XP {stats['xp_current']}/{stats['xp_needed']} "
          f"| streak {stats['streak']}d | contrib(month) {stats['contrib_month']}/{config['monthly_contribution_goal']} "
          f"| titles {len(unlocked)} | skills {len(known_skills)} | penalty_active {bool(pending_penalty)} "
          f"| new_notifications {len(new_notifications)}")


if __name__ == "__main__":
    main()

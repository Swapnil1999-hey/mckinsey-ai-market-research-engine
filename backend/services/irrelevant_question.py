"""
irrelevant_question.py
======================
Detects and answers questions that are outside the scope of the
McKinsey AI Market Research & Strategy Engine.

Flow
----
1.  classify_query(query) -> ("relevant" | "irrelevant", category, reason)
    Uses a lightweight keyword/pattern check first (zero latency, no API call).
    If the query is clearly market-research related it is passed through immediately.

2.  irrelevant_answer(query, category) -> str
    Returns a friendly, helpful answer for the irrelevant question
    (e.g. current date/time for weather questions) and politely
    redirects the user back to the platform's purpose.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# IST offset  (UTC+5:30)
# ---------------------------------------------------------------------------
IST = timezone(timedelta(hours=5, minutes=30))


def _now_ist() -> datetime:
    return datetime.now(IST)


# ---------------------------------------------------------------------------
# Category definitions
# Each entry: (category_name, [regex patterns that signal this category])
# ---------------------------------------------------------------------------
_IRRELEVANT_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "weather",
        [
            r"\bweather\b",
            r"\bforecast\b",
            r"\brain(ing|fall)?\b",
            r"\btemperature\b",
            r"\bhumidity\b",
            r"\bsunny\b",
            r"\bcloudy\b",
            r"\bsnow(ing|fall)?\b",
            r"\bwind\b.*\bspeed\b",
            r"\bwill it rain\b",
        ],
    ),
    (
        "date_time",
        [
            r"\bwhat (is |'?s )?(the )?(current )?(date|day|time|year|month)\b",
            r"\bwhat (day|date|time) (is it|today)\b",
            r"\bwhat is today\b",
            r"\btoday'?s? (date|day|time)\b",
            r"\bcurrent time\b",
            r"\bright now\b.*\btime\b",
            r"\bwhat time is it\b",
            r"\btoday date\b",
            r"\btoday'?s date\b",
        ],
    ),
    (
        "sports",
        [
            r"\bscore\b.*\b(match|game|ipl|cricket|football|soccer|nba|nfl|tennis)\b",
            r"\b(ipl|cricket|football|soccer|nba|nfl|tennis|badminton)\b.*\bscore\b",
            r"\bwho (won|is winning|scored)\b",
            r"\bfixture\b",
            r"\bstandings?\b.*\b(league|tournament)\b",
        ],
    ),
    (
        "entertainment",
        [
            r"\b(movie|film|series|show|episode|season)\b.*\b(watch|stream|release|trailer)\b",
            r"\bnetflix\b.*\bwatch\b",
            r"\blatest\b.*\b(song|album|movie)\b",
            r"\bbox office\b",
        ],
    ),
    (
        "personal_advice",
        [
            r"\brelationship (advice|help|problem)\b",
            r"\bhow (do i|can i|should i)\b.*\b(feel|deal|cope|handle)\b",
            r"\bi (feel|am feeling|am) (sad|depressed|lonely|anxious|stressed)\b",
            r"\bmental health\b",
            r"\btherapist\b",
        ],
    ),
    (
        "cooking_recipes",
        [
            r"\brecipe\b",
            r"\bhow (do i|to) (cook|bake|make|prepare)\b",
            r"\bingredients?\b.*\b(dish|meal|food)\b",
            r"\b(calories|nutrition|diet plan)\b",
        ],
    ),
    (
        "general_knowledge",
        [
            r"\bwho is\b.*(actor|actress|singer|celebrity|president|prime minister|king|queen)\b",
            r"\bwhat is\b.*(capital of|population of|currency of|language of)\b",
            r"\bhow (tall|old|many)\b",
            r"\bfun fact\b",
            r"\btell me a joke\b",
            r"\bwrite me a poem\b",
        ],
    ),
    (
        "crypto_stock_trading",
        [
            r"\b(bitcoin|ethereum|crypto|dogecoin|nft)\b.*\b(price|value|buy|sell|invest)\b",
            r"\bstock (price|ticker|chart)\b",
            r"\bshould i (buy|sell|invest in)\b",
            r"\b(trading|day trading)\b.*\b(tips|signals|strategy)\b",
        ],
    ),
    (
        "travel_booking",
        [
            r"\bflight (ticket|booking|cheap)\b",
            r"\bbook (a hotel|flights|a trip)\b",
            r"\bhow (to|do i) (get to|travel to|reach)\b",
            r"\bvisa (requirements|application)\b",
        ],
    ),
    (
        "health_medical",
        [
            r"\b(symptoms of|cure for|treatment for|medicine for)\b",
            r"\bam i (pregnant|sick|ill|healthy)\b",
            r"\bshould i (take|stop) (this medication|pills)\b",
            r"\bhome remedy\b",
        ],
    ),
]

# ---------------------------------------------------------------------------
# Keywords that strongly signal a RELEVANT (market research) query.
# If any of these appear, skip the irrelevant check.
# ---------------------------------------------------------------------------
_RELEVANT_KEYWORDS = [
    "market",
    "competitor",
    "strategy",
    "industry",
    "growth",
    "revenue",
    "investment",
    "startup",
    "enterprise",
    "sector",
    "analysis",
    "research",
    "consumer",
    "demand",
    "supply",
    "regulation",
    "regulatory",
    "esg",
    "valuation",
    "forecast",  # market forecast – different from weather forecast
    "trend",
    "disruption",
    "landscape",
    "competitive",
    "acquisition",
    "merger",
    "ipo",
    "gdp",
    "inflation",
    "trade",
    "export",
    "import",
    "digital",
    "fintech",
    "healthtech",
    "edtech",
    "saas",
    "b2b",
    "b2c",
    "ecommerce",
    "supply chain",
    "go-to-market",
]


def classify_query(query: str) -> tuple[str, str, str]:
    """
    Returns (verdict, category, reason).
      verdict   : "relevant" | "irrelevant"
      category  : e.g. "weather", "sports", "" for relevant
      reason    : human-readable explanation
    """
    q_lower = query.lower().strip()

    # 1. Fast-pass: clearly relevant to market research
    for kw in _RELEVANT_KEYWORDS:
        if kw in q_lower:
            return "relevant", "", f"Contains market-research keyword: '{kw}'"

    # 2. Check irrelevant categories
    for category, patterns in _IRRELEVANT_PATTERNS:
        for pat in patterns:
            if re.search(pat, q_lower):
                # Special case: "forecast" in weather context (not market)
                if category == "weather" and "market" in q_lower:
                    continue
                return (
                    "irrelevant",
                    category,
                    f"Matched irrelevant pattern '{pat}' in category '{category}'",
                )

    # 3. Default: treat as potentially relevant (don't block ambiguous queries)
    return "relevant", "", "No irrelevant pattern matched; treating as market research query"


# ---------------------------------------------------------------------------
# Response templates per category
# ---------------------------------------------------------------------------

def irrelevant_answer(query: str, category: str) -> dict:
    """
    Returns a structured dict with:
      is_irrelevant  : True
      category       : str
      answer         : str  – friendly helpful text
      redirect       : str  – nudge back to the platform
    """
    now = _now_ist()
    day_name   = now.strftime("%A")                         # e.g. Saturday
    date_str   = now.strftime("%d %B %Y")                  # e.g. 14 November 2026
    time_str   = now.strftime("%I:%M %p IST")              # e.g. 01:08 PM IST
    redirect   = (
        "I'm specialised for the **McKinsey AI Market Research & Strategy Engine**. "
        "Feel free to ask me a business or market research question and I'll run a "
        "full evidence-backed analysis for you! 🔍"
    )

    if category == "weather":
        answer = (
            f"I can't check live weather data, but here's what I know:\n\n"
            f"📅 **Today:** {day_name}, {date_str}\n"
            f"🕐 **Local time (IST):** {time_str}\n\n"
            f"For real-time weather please visit:\n"
            f"- 🌐 [Google Weather](https://www.google.com/search?q=weather+today)\n"
            f"- 🇮🇳 [India Meteorological Department](https://mausam.imd.gov.in/)\n"
            f"- 📱 AccuWeather / your phone's weather app"
        )

    elif category == "date_time":
        answer = (
            f"🗓️ **Today is {day_name}, {date_str}**\n"
            f"🕐 **Current time:** {time_str} (UTC+5:30)"
        )

    elif category == "sports":
        answer = (
            f"I don't have live sports scores — I'm a market research assistant!\n\n"
            f"For live scores try:\n"
            f"- [ESPN](https://www.espn.com)\n"
            f"- [Cricbuzz](https://www.cricbuzz.com) for cricket\n"
            f"- [Google](https://www.google.com/search?q=live+score) → search 'live score'"
        )

    elif category == "entertainment":
        answer = (
            f"I specialise in market intelligence, not entertainment!\n\n"
            f"For movies and shows:\n"
            f"- [IMDb](https://www.imdb.com)\n"
            f"- [Netflix](https://www.netflix.com)\n"
            f"- [JustWatch](https://www.justwatch.com) to find where to stream"
        )

    elif category == "personal_advice":
        answer = (
            f"I'm a business research tool and not equipped to give personal or emotional advice.\n\n"
            f"If you need support, please reach out to a trusted person, counsellor, or "
            f"a helpline in your area. You matter. 💙\n\n"
            f"For India: **iCall** – 9152987821 | **Vandrevala Foundation** – 1860-2662-345"
        )

    elif category == "cooking_recipes":
        answer = (
            f"Cooking tips are outside my expertise! Try:\n"
            f"- [AllRecipes](https://www.allrecipes.com)\n"
            f"- [Tasty](https://tasty.co)\n"
            f"- [Cookpad](https://cookpad.com)"
        )

    elif category == "crypto_stock_trading":
        answer = (
            f"I don't provide real-time prices or trading signals.\n\n"
            f"However, I **can** help you research the **market landscape** around crypto/fintech "
            f"sectors, competitor strategies, or regulatory environments. Just ask!\n\n"
            f"For live prices: [CoinMarketCap](https://coinmarketcap.com) | "
            f"[Yahoo Finance](https://finance.yahoo.com)"
        )

    elif category == "travel_booking":
        answer = (
            f"Flight and hotel bookings are outside my scope! Try:\n"
            f"- [Google Flights](https://www.google.com/flights)\n"
            f"- [MakeMyTrip](https://www.makemytrip.com)\n"
            f"- [Booking.com](https://www.booking.com)"
        )

    elif category == "health_medical":
        answer = (
            f"I'm a market research tool, not a medical assistant.\n\n"
            f"⚠️ **Please consult a qualified doctor or pharmacist** for health concerns.\n\n"
            f"I *can* help you research the **healthcare market landscape**, "
            f"hospital sector trends, or health-tech competitors if that's useful!"
        )

    else:  # general_knowledge or unrecognised
        answer = (
            f"That question is outside the scope of the McKinsey AI Market Research Engine.\n\n"
            f"I'm designed to help with **business questions, market research, competitive "
            f"analysis, and strategy briefs**."
        )

    return {
        "is_irrelevant": True,
        "category": category,
        "query": query,
        "answer": answer,
        "redirect": redirect,
        "timestamp": now.isoformat(),
    }

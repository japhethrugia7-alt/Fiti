import random

ICEBREAKERS = [
    "If you could visit anywhere in Kenya right now, where would it be?",
    "What's a food you could eat every day and never get tired of?",
    "What's the best matatu playlist you've ever heard?",
    "Are you a chapati or ugali person, and why?",
    "What's something you're weirdly good at?",
    "What's your go-to weekend plan?",
    "What's a song that instantly puts you in a good mood?",
    "Nyama choma or fish — settle it once and for all.",
    "What's the last thing that made you laugh out loud?",
    "If you had a free flight anywhere today, where would you go?",
    "What's a small thing that makes your day better?",
    "What's your idea of a perfect Saturday?",
]


def random_icebreaker() -> str:
    return random.choice(ICEBREAKERS)

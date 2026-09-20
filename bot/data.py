TRIGGERS = {
    "lolroaster": {
        "type": "reaction",
        "responses": ["🔥", "🗿", "🦧"],
    },
    "chud": {
        "type": "reply",
        "responses": ["Billy's favorite word!"],
    },
    "kfc": {
        "type": "reply",
        "responses": [
            "Reminder to stop eating kfc you walnut",
            "Mmmm chimken",
            "Is Mr. Sanders in?",
        ],
    },
    "kira": {
        "type": "file",
        "texts": ["Kira says what?"],
        "files": ["gifs/kira.gif"],
    },
}

WORDLE_RESPONSES = {
    "1/6": ["Yeah nah, they HAVE to be cheating 💀", "BRO WHAT!?!?!"],
    "2/6": ["Just shy of perfection... ⭐"],
    "3/6": [
        "3/6 reduces to 1/2, which is exactly the measurement in ass you gave of effort 😶‍🌫️"
    ],
    "4/6": ["But it's ok, everyone mistypes 3 times in a row sometimes 🫃"],
    "5/6": [
        "The monkey with a typewriter that has infinite time theorem is just a theorem, but I praise the attempt at seeing if it works in wordle! 🦧"
    ],
    "6/6": ["Excused -> (if english isn't their first language) 😂"],
    "X/6": ["Ain't no way 😭"],
}


def fresh_wordle_scores() -> dict[str, list[str]]:
    return {
        "1/6": [],
        "2/6": [],
        "3/6": [],
        "4/6": [],
        "5/6": [],
        "6/6": [],
        "X/6": [],
    }

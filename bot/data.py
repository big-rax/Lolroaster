TRIGGERS = {
    "lolroaster": {
        "type": "reaction",
        "responses": ["🔥", "🗿", "🦧"],
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

# GIF links for /freaky. One is picked at random each time; Discord embeds the link as a GIF.
# To add one: open the GIF on tenor.com or giphy.com, click "Copy link", paste it here.
FREAKY_GIFS = [
    "https://klipy.com/gifs/sonic-69",
    "https://klipy.com/gifs/gato-cat-58",
    "https://klipy.com/gifs/3-gato",
    "https://klipy.com/gifs/paulaliensmirk",
    "https://klipy.com/gifs/rage-baited-diemarchive",
    "https://klipy.com/gifs/lick-suck-2"
]

WORDLE_RESPONSES = {
    "1/6": ["Yeah nah, they HAVE to be cheating 💀", "BRO WHAT!?!?!"],
    "2/6": ["what a snipe"],
    "3/6": [
        "man get that pepper off of there"
    ],
    "4/6": ["🫃"],
    "5/6": [
        "probably button mashes in smash bros."
    ],
    "6/6": ["oh lawd"],
    "X/6": ["ain't no way 😭"],
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

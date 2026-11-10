from __future__ import annotations
import discord
from discord import app_commands

# Each /help page: title, intro line, list of (command or heading, description, admin_only), footer.
# Entries that don't start with "/" are shown as bold headings instead of commands.
HELP_PAGES: dict[str, dict] = {
    "overview": {
        "label": "Overview",
        "emoji": "🔥",
        "title": "Lolroaster help",
        "intro": "I roast your League games, Wordle scores and gaming habits. Everything social is opt-in.",
        "items": [
            ("Get started",
             "1. `/roast toggle` to opt in\n"
             "2. `/lol link` to connect your Riot ID\n"
             "3. `/lol live` next time you're in a game", False),
            ("Pick a category below", "League, roasts, game pings and settings each have their own page.", False),
        ],
        "footer": "Run /help anytime",
    },
    "lol": {
        "label": "League (/lol)",
        "emoji": "⚔️",
        "title": "League (/lol)",
        "intro": "Link your Riot ID once, then everything else just works.",
        "items": [
            ("/lol link", "Connect your Riot ID and show your rank and top champs", False),
            ("/lol account", "Your linked account with Solo/Duo and Flex ranks", False),
            ("/lol mastery", "Your top champion masteries", False),
            ("/lol live", "Post a live game card that updates every minute", False),
            ("/lol lastgame", "Result of your (or a friend's) most recent game", False),
            ("/lol leaderboard", "Rank the server's opted-in players", False),
        ],
        "footer": "NA accounts only for now",
    },
    "roast": {
        "label": "Roasts (/roast)",
        "emoji": "😈",
        "title": "Roasts (/roast)",
        "intro": "The fun part.",
        "items": [
            ("/roast wordle", "Roast everyone from a Wordle group result", False),
            ("/roast toggle", "Opt in or out of being roasted", False),
        ],
        "footer": "Only opted-in players get roasted",
    },
    "pings": {
        "label": "Game pings and Steam",
        "emoji": "🎮",
        "title": "Game pings and Steam",
        "intro": "When an opted-in member starts a tracked game, I call them out, with playtime if it's embarrassing.",
        "items": [
            ("/roast game add / remove / list", "Choose which games trigger pings", False),
            ("/roast game channel", "Pick where pings are posted", True),
            ("/steam link / unlink", "Use your Steam playtime for more accurate roasts", False),
        ],
        "footer": "Tracked by default: League, Deadlock, Neovim",
    },
    "settings": {
        "label": "Settings and opt-in",
        "emoji": "⚙️",
        "title": "Settings and opt-in",
        "intro": "Control who and where I roast.",
        "items": [
            ("/roast toggle", "Opt yourself in or out", False),
            ("/roast toggle-user", "Opt someone else out", True),
            ("/settings", "Turn me on or off and pick my channels", True),
            ("/channel list", "See which channels I talk in", False),
        ],
        "footer": "Admin commands need Manage Server",
    },
}


# Builds the embed for one /help page.
def build_help_embed(key: str) -> discord.Embed:
    page = HELP_PAGES[key]
    lines = [page["intro"], ""]
    for name, desc, admin in page["items"]:
        head = f"`{name}`" if name.startswith("/") else f"**{name}**"
        if admin:
            head += " · *Admin*"
        lines.append(f"{head}\n{desc}\n")
    embed = discord.Embed(title=page["title"], description="\n".join(lines).strip(), color=discord.Color.blue())
    embed.set_footer(text=page["footer"])
    return embed


# Dropdown that swaps the /help embed in place. The message is ephemeral, so only the person who ran /help sees it.
class HelpView(discord.ui.View):
    def __init__(self, current: str = "overview"):
        super().__init__(timeout=300)
        self.page_select.options = [
            discord.SelectOption(label=p["label"], value=k, emoji=p["emoji"], default=(k == current))
            for k, p in HELP_PAGES.items()
        ]

    @discord.ui.select(placeholder="Pick a category...")
    async def page_select(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        key = select.values[0]
        await interaction.response.edit_message(embed=build_help_embed(key), view=HelpView(key))


def register_help(tree: app_commands.CommandTree) -> None:
    @tree.command(name="help", description="See what Lolroaster can do and how to use it")
    async def help_command(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=build_help_embed("overview"), view=HelpView(), ephemeral=True)

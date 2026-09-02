import sys
from argparse import ArgumentParser
from pprint import pprint
from ovos_utils import camel_case_split
from py_music_assistant import SimpleHTTPMusicAssistantClient
from ovos_config.config import MycroftUserConfig


def _select_default(players, default_arg):
    """Pick the index of the default player.

    ``default_arg`` may be a player index, a player_id, or ``None``. When
    ``None`` and stdin is not interactive, raises ``SystemExit`` with a
    clear error instead of letting ``input()`` raise ``EOFError``.
    """
    if len(players) == 1:
        return 0

    if default_arg is not None:
        for idx, player in enumerate(players):
            if str(idx) == str(default_arg) or player.player_id == default_arg:
                return idx
        raise SystemExit(f"ERROR: no player matches --default '{default_arg}'")

    for idx, player in enumerate(players):
        d = f"{player.name}:{player.provider}:{player.player_id}"
        print(f"{idx} - {d}")

    if not sys.stdin.isatty():
        raise SystemExit(
            "ERROR: multiple players found and no --player/--default given; "
            "stdin is not interactive. Re-run with --default <index-or-player-id>."
        )

    return int(input("select default mass device: "))


def main():
    parser = ArgumentParser(description="Auto configure Music Assistant devices under mycroft.conf")
    parser.add_argument("--url", help="Music Assistant server url")
    parser.add_argument("--default", "--player", dest="default",
                         help="index or player_id of the default player "
                              "(required for non-interactive use when multiple players are found)")
    args = parser.parse_args()

    print(
        """This script will auto configure Music Assistant devices under your mycroft.conf\nMake sure your Music Assistant server is accessible from this device""")

    url = args.url or input("Please enter your Music Assistant server url: ")

    api = SimpleHTTPMusicAssistantClient(url)
    print("\nScanning...")
    players = [player for player in api.get_players() if player.provider != "builtin_player"]

    if not players:
        print("ERROR: no mass devices found")
        exit(1)

    for player in players:
        print(f"    - Found player: {player.name} - {player.provider}:{player.player_id}")

    cfg = MycroftUserConfig()

    default = _select_default(players, args.default)

    for idx, player in enumerate(players):
        d = player.player_id
        normd = f"{player.name}:{player.provider}".replace(" ", "-").strip()
        is_default = idx == default

        if "media" not in cfg:
            cfg["media"] = {}
        if "audio_players" not in cfg["media"]:
            cfg["media"]["audio_players"] = {}

        if is_default:
            if "Audio" not in cfg:
                cfg["Audio"] = {}
            if "backends" not in cfg["Audio"]:
                cfg["Audio"]["backends"] = {}
            cfg["Audio"]["backends"]["mass-" + normd] = {
                "type": "ovos_mass",
                "identifier": d,
                "url": url,
                "player_type": player.provider,
                "active": True
            }

        cfg["media"]["audio_players"]["mass-" + normd] = {
            "module": "ovos-media-audio-plugin-mass",
            "identifier": d,
            "url": url,
            "player_type": player.provider,
            "aliases": [player.name, camel_case_split(player.name)],
            "active": is_default
        }
    cfg.store()

    print("\nmycroft.conf updated!")

    print("\n# Legacy Audio Service:")
    pprint(cfg["Audio"])

    print("\n# ovos-media Service:")
    pprint(cfg["media"])


if __name__ == "__main__":
    main()

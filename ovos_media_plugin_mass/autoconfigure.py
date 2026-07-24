from pprint import pprint
from ovos_utils import camel_case_split
from py_music_assistant import SimpleHTTPMusicAssistantClient
from ovos_config.config import UserConfig


def main():
    print(
        """This script will auto configure Music Assistant devices under your mycroft.conf\nMake sure your Music Assistant server is accessible from this device""")

    url = input("Please enter your Music Assistant server url: ")

    api = SimpleHTTPMusicAssistantClient(url)
    print("\nScanning...")
    players = [player for player in api.get_players() if player.provider != "builtin_player"]

    if not players:
        print("ERROR: no mass devices found")
        exit(1)

    for player in players:
        print(f"    - Found player: {player.name} - {player.provider}:{player.player_id}")

    cfg = UserConfig()

    if len(players) == 1:
        default = 0
    else:
        for idx, player in enumerate(players):
            d = f"{player.name}:{player.provider}:{player.player_id}"
            print(f"{idx} - {d}")
        default = int(input("select default mass device:"))

    for idx, player in enumerate(players):
        d = player.player_id
        normd = f"{player.name}:{player.provider}".replace(" ", "-").strip()
        if "media" not in cfg:
            cfg["media"] = {}
        if "audio_players" not in cfg["media"]:
            cfg["media"]["audio_players"] = {}

        if idx == default:
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
            "active": True
        }
    cfg.store()

    print("\nmycroft.conf updated!")

    print("\n# Legacy Audio Service:")
    pprint(cfg["Audio"])

    print("\n# ovos-media Service:")
    pprint(cfg["media"])


if __name__ == "__main__":
    main()

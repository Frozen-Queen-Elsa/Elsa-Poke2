"""
The launcher for pokeball.py which verifies Python version.
Also serves as gateway for system args.
"""
import argparse
import sys

from pokeball import PokeBall

if __name__ == "__main__":
    if sys.version_info < (3,7):
        print(
            f"Looks like you are running Python version v{sys.version.split()[0]}.\n"
            "But you require version v3.7 or v3.8.\n"
            "Please retry after updating to the latest version.\n"
        )
    else:
        parser = argparse.ArgumentParser()
        default_dict = {
            "config_path": "config.json",
            "pokeclasses_path": "pokeclasses.txt",
            "pokemodel_path": "pokemodel.pth",
            "pokedb_path": "pokeball.db",
            "pokeranks_path": "pokeranks.json",
            "error_log_path": "errors.log"
        }
        for key, val in default_dict.items():
            parser.add_argument(
                f'--{key}',
                default=f'data/{val}'
            )
        parsed = parser.parse_args()
        bot = PokeBall(**{
            key: getattr(parsed, key)
            for key in default_dict
        })
        bot.run()

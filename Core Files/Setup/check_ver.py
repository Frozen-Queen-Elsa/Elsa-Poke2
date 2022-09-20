"""
Python Version Validator and Pytorch setup
"""

import json
import os
import subprocess
import sys
import urllib.request

def get_mathver(ver: str) -> int:
    """
    Converts version string into integer
    """
    version_digits = ver.split('v')[1].split('.')
    lvd = len(version_digits)
    return sum(
        int(version_digits[i]) * pow(10, lvd - i)
        for i in range(lvd)
    )

def validate_py_ver():
    """
    Validates whether python 3.7 or 3.8 is installed.
    """
    if all(
        not sys.version.startswith(ver)
        for ver in ["3.7", "3.8"]
    ):
        print(
            "\nInvalid Version of Python detected!\n"
            "Install either Python 3.7 or 3.8 to proceed."
        )
        sys.exit(-1)

def check_updates():
    """
    Compares local version with the remote version before installing.
    """
    with open('../../_version.json') as vers_fl:
        local_version = json.load(vers_fl)["version"]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" + \
            "AppleWebKit/537.36 (KHTML, like Gecko)" + \
            "Chrome/77.0.3865.90 Safari/537.36",
        "Accept": "text/json"
    }
    remote_version_url = "https://raw.githubusercontent.com/Hyperclaw79/" + \
        "PokeBall-SelfBot/master/_version.json"
    req =  urllib.request.Request(
        remote_version_url,
        headers=headers
    )
    with urllib.request.urlopen(req) as resp:
        response = resp.read()
    remote_version = json.loads(response)["premium_version"]
    if get_mathver(remote_version) > get_mathver(local_version):
        print(
            "\nLooks like there is a new update available!\n"
            "Download the latest version from the google drive link.\n"
            f"Your version: {local_version}\n"
            f"Available version: {remote_version}\n"
        )
        choices = ["Yes", "No"]
        print(
            (
                "Would you like to continue with this version?\n"
                + '\n'.join(
                    f"{idx + 1}. {choice}"
                    for idx, choice in enumerate(choices)
                )
            )
        )
        choice = input("\n")
        if choice.lower() in ["yes", "y", "1"]:
            print(
                f"\nAlright, going forward with {local_version}.\n"
                "It's highly recommended to update to the latest version asap.\n"
                "Installing necessary modules...\n"
            )
        else:
            sys.exit(0)

def install_vc():
    """
    Attempts to install VC++ (required to build PyTorch).
    Silently ignores errors (usually happens if VC++ is already installed.)
    """
    vcpath = os.path.join(
        os.getcwd(),
        'vcredist',
        'VC_redist.x64.exe'
    )
    try:
        subprocess.run(
            f"{vcpath} /quiet /norestart",
            check=True
        )
    except: # pylint: disable=bare-except
        pass

def install_torch():
    """
    Installs PyTorch v1.7.1, on which the CNN model was trained.
    Also installs other dependencies in requirements.txt.
    """
    if len(sys.argv) < 2:
        pip_path = 'pip'
        reqs_path = 'requirements.txt'
    else:
        reqs_path = os.path.join(sys.argv[-1], 'requirements.txt')
        pip_path = os.path.join(sys.argv[-2], 'pip')
    pips1 = subprocess.run(
        f'"{pip_path}" uninstall -y discord.py',
        check=True
    )
    pips2 = subprocess.run(
        f'"{pip_path}" install -r "{reqs_path}"',
        check=True
    )
    if all(
        res.returncode == 0
        for res in (pips1, pips2)
    ):
        pips = subprocess.run(
            f'"{pip_path}" install torch==1.7.1+cpu torchvision==0.8.2+cpu '
            '-f https://download.pytorch.org/whl/torch_stable.html',
            check=True
        )
        if pips.returncode == 0:
            print(
                "\nSuccesfully installed all modules!\n"
                "Proceed to setting up your configs.\n"
            )
        else:
            print("\nPip installation failed.")
    else:
        print("\nPip installation failed.")

if __name__ == "__main__":
    # Check for Py3.7+
    validate_py_ver()

    # Check for New Version
    check_updates()

    # Install VC++
    install_vc()

    # Install PyTorch
    install_torch()

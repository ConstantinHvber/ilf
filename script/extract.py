import os
import json
import shutil
import argparse
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import *
import jsoncfg

accounts = [
    "1c6dbb1fe61bbb7c256f0ffcbd34087e211173dbc8454220b8b166ed6ada5c00",
    "b1cff43bf95333788b080b6cd5c5e2fcbe321ccd4132ed80cb3e72478c69e9a7",
    "aa3eeb453426d9c9292f89be5fa7e6caa0330d312255f84c0caa6764ae1adf00",
    "34a5a824b045c9ce797589d334394c11ee28d9cd8757f1a9b0ccf0fd0008c641",
    "a7a163dcb33958498cf5736282f53e39bd6cb7a58f5d4a948445dc86faa34f90",
]
amount = "100000000000000000000000000000"


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--proj", dest="proj", type=str, required=True)
    parser.add_argument("--port", dest="port", type=int, default=8545)
    args = parser.parse_args()
    return args

@contextmanager
def run_ganache(port):
    account_cmd = []
    for account in accounts:
        account_cmd.append("--account=0x{},{}".format(account, amount))

    cmd = [
        "ganache-cli",
        "-p",
        str(port),
        "--gasLimit",
        "0xfffffffffff",
    ] + account_cmd
    proc = subprocess.Popen(cmd)

    try:
        yield proc
    finally:
        proc.terminate()


def load_config(cfg: Path):
    contents = cfg.open().read()
    just_obj = contents[contents.find("{") : contents.rfind("}") + 1]
    return jsoncfg.loads(just_obj)


def dump_config(cfg: Path, obj: Any):
    contents = "module.exports = \n{}".format(json.dumps(obj, indent=2))
    cfg.open("w").write(contents)


@contextmanager
def config_switcharoo(config: Path, port: int):
    backup_config = Path(str(config) + "_bak")
    shutil.copy(config, backup_config)

    dd = load_config(config)
    try:
        dd["networks"]["development"]["port"] = int(port)
    except KeyError:
        raise
    dump_config(config, dd)

    try:
        yield
    finally:
        shutil.copy(backup_config, config)
        os.remove(backup_config)


def extract_transactions(project_dir, port):
    project_dir = Path(project_dir)
    os.chdir(project_dir)

    config = project_dir / "truffle-config.js"
    with config_switcharoo(config, port):
        assert 0 == subprocess.call("truffle compile".split())
        assert 0 == subprocess.call("truffle deploy".split())
        extract_js_path = Path(__file__).parent / "extract.js"
        assert 0 == subprocess.call("truffle exec {}".format(extract_js_path).split())

def main():
    args = get_args()

    with run_ganache(args.port):
        extract_transactions(args.proj, args.port)


if __name__ == "__main__":
    main()
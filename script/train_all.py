import re
import sys
import glob
import time
import json
import subprocess
from pathlib import Path
from tqdm import tqdm

VISITED_LOG_FILE = Path("/tmp/ilf_visited_log_file.json")
TRAINED_LOG_FILE = Path("/tmp/ilf_trained_log_file.json")


def main(projects_dir_name: str, output_dir: str, visited_log_file = None):
    visited_files = set()

    visited_log_file = Path(visited_log_file or VISITED_LOG_FILE)
    if visited_log_file.exists():
        with visited_log_file.open() as fr:
            visited_files = set(json.load(fr))

    trained_files = set()
    if TRAINED_LOG_FILE.exists():
        with TRAINED_LOG_FILE.open() as fr:
            trained_files = set(json.load(fr))

    untrained_files = visited_files - trained_files

    projects_dir = Path(projects_dir_name)
    assert projects_dir.exists()

    try:
        files_progress = tqdm(untrained_files)
        for file in files_progress:
            truffle_file = projects_dir / file
            root_dir = truffle_file.parent

            files_progress.set_description(root_dir.name, refresh=True)

            # hacking begins again
            deploy_file = root_dir / "migrations" / "2_deploy_contracts.js"
            try:
                contract_name = get_that_damn_contract_name_again(deploy_file)
            except ValueError:
                continue

            cmd_text = f"python3 -m ilf --proj {root_dir.resolve()} --contract {contract_name} --limit 2000 --fuzzer symbolic --dataset_dump_path {output_dir}/{root_dir.name}.data"
            print(f"Will run {cmd_text}")
            cmd = subprocess.run(cmd_text.split())

            if cmd.returncode == 0:
                trained_files.add(file)

    except Exception:
        print()
        print(f"Processing {file} failed unexpectedly")

    except KeyboardInterrupt:
        pass

    finally:
        with TRAINED_LOG_FILE.open("w") as fw:
            json.dump(list(trained_files), fw)


identifier = r"[a-zA-Z_$][a-zA-Z_$0-9]*"
contract_name_re = re.compile(fr"var ({identifier}) =")


def get_that_damn_contract_name_again(deploy_file: Path) -> str:
    contents = deploy_file.open().read()

    [i_hope_for_exact_match] = contract_name_re.findall(contents)
    return i_hope_for_exact_match


if __name__ == "__main__":
    [projects_dir, output_dir, *rest] = sys.argv[1:]

    visited_log_file = rest[0] if len(rest) > 0 else None

    main(projects_dir, output_dir ,visited_log_file=visited_log_file)
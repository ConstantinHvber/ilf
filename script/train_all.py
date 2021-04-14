import re
import sys
import glob
import time
import json
import threading
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

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

    write_lock = threading.Lock()

    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            for file in untrained_files:

                def _closure(current_file):
                    truffle_file = projects_dir / current_file
                    root_dir = truffle_file.parent

                    # hacking begins again
                    deploy_file = root_dir / "migrations" / "2_deploy_contracts.js"
                    try:
                        contract_name = get_that_damn_contract_name_again(deploy_file)
                    except ValueError:
                        return

                    cmd_text = f"python3 -m ilf --proj {root_dir.resolve()} --contract {contract_name} --limit 2000 --fuzzer symbolic --dataset_dump_path {output_dir}/{root_dir.name}.data --execution ./execution_safe.so"
                    print(f"Will run {cmd_text}")
                    cmd = subprocess.run(cmd_text.split())

                    if cmd.returncode == 0:
                        with write_lock:
                            trained_files.add(current_file)

                executor.submit(_closure, file)


    except Exception:
        pass

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
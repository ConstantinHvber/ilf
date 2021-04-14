import glob
import time
import json
import subprocess
from pathlib import Path
from tqdm import tqdm

EXTRACT_SCRIPT = (Path(__file__).parent / "extract.py").resolve()
assert EXTRACT_SCRIPT.exists()

VISITED_LOG_FILE = Path("/tmp/ilf_visited_log_file.json")
FAILED_LOG_FILE = Path("/tmp/ilf_failed_log_file.json")


def main(dry_run=False):
    visited_files = set()
    if VISITED_LOG_FILE.exists():
        with VISITED_LOG_FILE.open() as fr:
            visited_files = set(json.load(fr))

    failed_files = set()
    failed_files_detail = dict()
    if FAILED_LOG_FILE.exists():
        with FAILED_LOG_FILE.open() as fr:
            failed_files_detail = json.load(fr)
            failed_files = set(failed_files_detail.keys())

    print(f"Starting with {len(visited_files)} already visited files")

    processed_files = set()

    try:
        while True:
            files = set(glob.glob("./**/truffle-config.js", recursive=True))
            files -= failed_files

            new_files = files - visited_files

            print(f"We have {len(new_files)} new files")

            if dry_run:
                time.sleep(10)
                continue

            files_progress = tqdm(new_files)
            for file in files_progress:
                truffle_file = Path(file)
                root_dir = truffle_file.parent

                files_progress.set_description(root_dir.name, refresh=True)

                # do stuff
                cmd = subprocess.run(f"python3 {EXTRACT_SCRIPT} --proj {root_dir}".split(), capture_output=True)

                if cmd.returncode != 0:
                    failed_files_detail[file] = cmd.stderr.decode("utf8")
                    failed_files.add(file)

                    # raise Exception("Command failed")


                processed_files.add(file)

            visited_files |= processed_files

    except Exception:
        print()
        print(f"Processing {file} failed unexpectedly")

    except KeyboardInterrupt:
        pass

    finally:
        visited_files |= processed_files

        with VISITED_LOG_FILE.open("w") as fw:
            json.dump(list(visited_files), fw)

        with FAILED_LOG_FILE.open("w") as fw:
            json.dump(failed_files_detail, fw)

        print()
        print(f"Processed successfuly {len(processed_files)} new files")


if __name__ == "__main__":
    main()
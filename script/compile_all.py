import glob
import threading
import subprocess
from pathlib import Path
from typing import *
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from .utils import progress_save

EXTRACT_SCRIPT = (Path(__file__).parent / "extract.py").resolve()
assert EXTRACT_SCRIPT.exists()


def main():
    with progress_save(visited=(set, list), failed_detail=(dict)) as (
        visited,
        failed_detail,
    ):
        executor = None
        p_bar = None
        failed = set(failed_detail.keys())
        processed = set()

        try:
            print("Counting files...")
            files = set(glob.iglob("./**/truffle-config.js", recursive=True))
            files -= failed
            new_files = files - visited

            print(f"We have {len(new_files)} new files")

            write_lock = threading.Lock()
            p_bar = tqdm(total=len(new_files))

            TNPREFIX = "ilf"
            DEFAULT_PORT = 8545
            with ThreadPoolExecutor(max_workers=8, thread_name_prefix=TNPREFIX) as executor:
                for _file in new_files:

                    def _closure(file):
                        t_name = threading.current_thread().name
                        t_id = int(t_name[len(TNPREFIX)+1:])
                        port = DEFAULT_PORT + t_id

                        truffle_file = Path(file).resolve()
                        root_dir = truffle_file.parent

                        cmd = subprocess.run(
                            f"python3 {EXTRACT_SCRIPT} --proj {root_dir} --port {port}".split(),
                            capture_output=True,
                        )

                        with write_lock:
                            p_bar.update(1)

                            if cmd.returncode != 0:
                                failed_detail[file] = cmd.stderr.decode("utf8")
                                failed.add(file)
                                p_bar.set_description(f"{root_dir.name} @ {t_id} FAILED", refresh=True)
                            else:
                                processed.add(file)
                                p_bar.set_description(f"{root_dir.name} @ {t_id} done", refresh=True)


                    executor.submit(_closure, _file)

        except KeyboardInterrupt:
            print()
            print("Exiting gracefully... (let the threads finish)")

        finally:
            if executor:
                executor.shutdown(cancel_futures=True)
            if p_bar:
                p_bar.close()
            visited |= processed


if __name__ == "__main__":
    main()
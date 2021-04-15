import re
import os
import json
import shutil
import subprocess
from pathlib import Path
from typing import *
from tqdm import tqdm

VISITED_LOG = Path("/mnt/hgfs/Shared/ilf_visited_log_file.json")
# ROOT_DIR = Path("/mnt/hgfs/Shared/trufflized_contracts")
ROOT_DIR = Path("/tmp/trufflized_contracts")

using_safemath_re = re.compile(r"(using SafeMath [^;]*?;)", re.MULTILINE)

sub_res = list(map(re.compile, [
    r"(assert\(b <= a[^;]*?;)"
    r"(require\(b <= a,[^;]*?;)"
]))
add_res = list(map(re.compile, [
    r"(assert\(c >= a[^;]*?;)",
    r"(require\(c >= a[^;]*?;)"
]))

safemath_replacements = sub_res + add_res

def main():
    succeeded = []
    try:
        # visited = json.load(open(VISITED_LOG))
        to_visit = list(ROOT_DIR.glob("./0xa*"))

        # projects: List[Path] = list(map(lambda s: (ROOT_DIR / s).parent, visited))

        p_bar = tqdm(to_visit)
        for proj in p_bar:
            [source] = list((proj / "contracts").glob("*.sol"))

            backup_source = Path(str(source) + "_bak")
            shutil.copy(source, backup_source)

            contents = source.open().read()

            for regex in safemath_replacements:
                new_contents = regex.sub(r"// \1 ", contents)

            if len(contents) == len(new_contents):
                continue

            source.open("w").write(new_contents)

            res = subprocess.call("truffle compile".split(), cwd=proj)
            if res == 0:
                succeeded.append(str(source))
            else:
                os.replace(backup_source, source)

            p_bar.set_description(f"Succeeded: {len(succeeded)}")

    except KeyboardInterrupt:
        pass

    finally:
        json.dump(succeeded, open("/tmp/removing_safemath.json", "w"))

if __name__ == "__main__":
    main()
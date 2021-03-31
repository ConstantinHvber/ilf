import argparse
import shutil
import subprocess
import os
from pathlib import Path

parser = argparse.ArgumentParser()

SOLC_VERSIONS = [
    "0.4.26",
    "0.5.16",
    "0.6.11",
]

PROJECT_TEMPLATE = "truffle_project/"
SOURCE_CONTRACT_FILE = PROJECT_TEMPLATE + "contracts/contract.sol"

DEPLOY_JS_FILE = PROJECT_TEMPLATE + "migrations/2_deploy_contracts.js"
DEPLOY_JS_FMT = """
var contract = artifacts.require("{contract}");

module.exports = function(deployer) {{
  deployer.deploy(contract);
}};
"""

parser.add_argument('--file', dest='file', type=str, default=None, required=True)
parser.add_argument('--contract', dest='contract', type=str, default=None, required=True)
parser.add_argument('--solc', dest='solc', type=str, choices=SOLC_VERSIONS, default=SOLC_VERSIONS[0])

args = parser.parse_args()

def main():
    source_file = Path(args.file).absolute()
    contract = args.contract
    solc_version = args.solc

    os.chdir(Path(__file__).parent)

    with open(DEPLOY_JS_FILE, "w") as fw:
        fw.write(DEPLOY_JS_FMT.format(contract=contract))

    shutil.copy(source_file, SOURCE_CONTRACT_FILE)

    assert 0 == subprocess.call("solc-select use {}".format(solc_version).split(" ")) # system-wide change

    assert 0 == subprocess.call("python3 script/extract.py --proj toolize/truffle_project/ --port 8545".split(" "), cwd="..")


if __name__ == "__main__":
    main()


from itertools import zip_longest
from pprint import pformat
import re
import json
import shutil
import hashlib
import argparse
import traceback
import subprocess
from dataclasses import dataclass, field, fields as dataclass_fields
from pathlib import Path
from typing import *
from collections import defaultdict
from tqdm import tqdm

parser = argparse.ArgumentParser()

parser.add_argument(
    "directory", type=str, default=None, help="Directory with solidity source files"
)
parser.add_argument(
    "--output",
    type=str,
    default=None,
    required=False,
    help="Output directory where to spill the results",
)
args = parser.parse_args()

dump_file_by_directory = lambda _dir: Path(
    "/tmp/trufflize_{}_project_versions.json".format(
        hashlib.md5(_dir.encode("utf8")).hexdigest()
    )
)


def main(directory: str, output: Optional[str]):
    sources_dir = Path(directory)
    assert sources_dir.is_dir()

    output_dir = Path(output or f"./trufflized_{sources_dir.name}")

    buckets: DefaultDict[str, List[str]] = defaultdict(list)

    dump_file = dump_file_by_directory(directory)
    if dump_file.exists():
        print(f"Loading from {dump_file}")
        buckets = json.load(dump_file.open())

    else:
        for source_file in sources_dir.iterdir():
            if source_file in IGNORED_FILES:
                continue

            if source_file.is_file() and source_file.suffix == ".sol":
                contents = source_file.open().read()
                versions = pragma_version_re.findall(contents)
                try:
                    suggested = resolve_solc_version(versions)
                except ValueError:
                    print(f"{source_file}: {versions}")
                    exit(1)

                resolved = SOLC_VERSIONS.get(suggested, "0.{}.{}".format(*suggested))

                # print(f"{source_file.stem}: {versions} -> {suggested} -> {resolved}")

                buckets[resolved].append(source_file.name)

        with dump_file.open("w") as fw:
            json.dump(buckets, fw)

    failed = dict()
    succeeded = 0

    for version, sources in tqdm(buckets.items()):

        # impromptu configs
        # if version in ["0.4.26"]:
        #     continue

        # if version not in ["0.5.16", "0.4.24"]:
        #     continue
        # end lulz

        assert 0 == subprocess.call(
            f"solc-select use {version}".split()
        ), f"Version {version} failed"

        for source_name in tqdm(sources, leave=False):
            source_file = sources_dir / source_name
            mini_proj_dir = output_dir / source_file.stem
            contracts_dir = mini_proj_dir / "contracts"
            output_file = contracts_dir / source_name
            migrations_dir = mini_proj_dir / "migrations"
            build_dir = mini_proj_dir / "build/contracts"

            try:
                extract = extract_from_source(source_file)
            except ExtractionError as e:
                failed[source_name] = str(e)

                if len(failed) % 1000 == 0:
                    total = succeeded + len(failed)
                    print(f"{succeeded=} {len(failed)=} {total=}")

                continue

            contracts_dir.mkdir(parents=True, exist_ok=True)
            migrations_dir.mkdir(parents=True, exist_ok=True)
            build_dir.mkdir(parents=True, exist_ok=True)

            truffle_config = mini_proj_dir / "truffle-config.js"
            truffle_config.open("w").write(
                TRUFFLE_CONFIG_CONTENTS_FMT.format(version=version)
            )

            migrations_file = migrations_dir / "1_initial_migration.js"
            migrations_file.open("w").write(TRUFFLE_MIGRATIONS_CONTENTS)
            shutil.copy(MIGRATIONS_FILE, build_dir / "Migrations.json")

            deploy_file = migrations_dir / "2_deploy_contracts.js"
            deploy_file.open("w").write(
                truffle_deploy_generate(contracts=[extract.main])
            )

            shutil.copy(source_file, output_file)

            succeeded += 1

    failed_debug_dump = "/tmp/failed_trufflize_projects.json"
    with open(failed_debug_dump, "w") as fw:
        json.dump(failed, fw)

    subprocess.call(f"code -r {failed_debug_dump}".split())

    # assert 0 == subprocess.call("solc-select use {}".format(solc_version).split(" "))


@dataclass
class ExtractionResult:
    main: str


class ExtractionError(Exception):
    ...


def extract_from_source(source_file: Path) -> ExtractionResult:
    try:
        ast = solidity_ast(source_file)
    except CompilationFailed as e:
        raise ExtractionError("AST: " + str(e)) from e

    try:
        abis = solidity_abis(source_file)
    except CompilationFailed as e:
        raise ExtractionError("ABIS " + str(e)) from e

    contracts = find_contracts(ast)
    last_ctr = contracts[-1]

    result = ExtractionResult(last_ctr.name)

    last_ctr_abi = abis[last_ctr.name]
    last_ctr_constructor = next(filter(lambda a: a.type == "constructor", last_ctr_abi), None)

    if not last_ctr_constructor:
        # raise ExtractionError("Constructor not found")

        # this is sorta fine actually?
        return result

    if len(last_ctr_constructor.inputs) != 0:
        # we can't handle that unfortunately
        raise ExtractionError("Constructor requires arguments")

    return result


class CompilationFailed(Exception):
    ...


def solidity_ast(file: Union[Path, str]):
    file = Path(file)
    cmd = subprocess.run(
        f"solc --ast-json {file.resolve()}".split(), capture_output=True
    )
    l_brace = cmd.stdout.find(b"{")
    r_brace = cmd.stdout.rfind(b"}")
    out = cmd.stdout[l_brace : r_brace + 1]
    if cmd.returncode != 0:
        raise CompilationFailed(cmd.stderr)
    if len(out) == 0:
        raise CompilationFailed("Empty stdout")

    return json.loads(cmd.stdout[l_brace : r_brace + 1])


def grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)


@dataclass(init=False)
class ContractABI:
    type: str
    inputs: List[Any]
    outputs: List[Any] = None
    stateMutability: str = None
    name: Optional[str] = None

    def __init__(self, **kwargs):
        names = set([f.name for f in dataclass_fields(self)])
        for k, v in kwargs.items():
            if k in names:
                setattr(self, k, v)


def solidity_abis(file: Union[Path, str]) -> Dict[str, List[ContractABI]]:
    file = Path(file)
    cmd = subprocess.run(f"solc --abi  {file.resolve()}".split(), capture_output=True)
    if cmd.returncode != 0:
        raise CompilationFailed(cmd.stderr)
    if len(cmd.stdout) == 0:
        raise CompilationFailed("Empty stdout")

    lines = cmd.stdout.lstrip().split(b"\n")
    abis = {}

    for [header, _, data, _] in grouper(lines, 4):
        if header is None or data is None:
            continue

        contract_name = header[header.find(b":") + 1 : header.rfind(b" ")].decode(
            "utf8"
        )
        abis[contract_name] = list(starstarmap(ContractABI, json.loads(data)))

    return abis


@dataclass(init=False)
class ContractAttributes:
    contractDependencies: List[str]
    contractKind: str
    documentation: str
    fullyImplemented: bool
    linearizedBaseContracts: List[int]
    name: str
    scope: int
    baseContracts: List[str] = field(default_factory=list)

    def __init__(self, **kwargs):
        names = set([f.name for f in dataclass_fields(self)])
        for k, v in kwargs.items():
            if k in names:
                setattr(self, k, v)

def starstarmap(function, iterable):
    for kwargs in iterable:
        yield function(**kwargs)


def _flatten_rec(obj):
    if isinstance(obj, (list, tuple)):
        for x in obj:
            yield from _flatten_rec(x)
    else:
        yield obj


def flatten(ll):
    return list(_flatten_rec(ll))


def _find_contracts_rec(ast):
    if ast["name"] == "ContractDefinition":
        return ast

    if "children" in ast.keys():
        return list(filter(None, map(_find_contracts_rec, ast["children"])))

    return None


def find_contracts(ast) -> List[ContractAttributes]:
    attrs = map(lambda dd: dd["attributes"], flatten(_find_contracts_rec(ast)))
    return list(starstarmap(ContractAttributes, attrs))


IGNORED_FILES = [
    "0xc0a47dfe034b400b47bdad5fecda2621de6c4d95.sol",  # this is not solidity
    "0xe75fa140f7c05077e05ffa0a9db227e32c80d5da.sol",  # again vyper
    "0xf6e8c835d43895cbf8cba18bdfcb348d7fd2cc58.sol",
    "0x2eb1e8fd394222df25638cfa8f0e5e7998a9dc1f.sol",
    "0x44d2142f6f3686c5ca7dbdd7c9d8882c630a0b86.sol",
    "0xa0cc94083c43a027071f6ccaee7251fbd818b7c6.sol",
]

MAX_PATCH = 69
MAX_MIN = 6

SOLC_VERSIONS = {
    (4, MAX_PATCH): "0.4.26",
    (5, MAX_PATCH): "0.5.16",
    (6, MAX_PATCH): "0.6.11",
}

identifier = r"[a-zA-Z_$][a-zA-Z_$0-9]*"
contract_name_re = re.compile(
    fr"(?:library|contract|interface)\s+({identifier})\s*(?:\{{|is|//|/\*)",
    re.MULTILINE,
)
pragma_version_re = re.compile(fr"^pragma\s+solidity\s+(.+?);", re.MULTILINE)
single_version_re = re.compile(r"(?:\^|[<=>]+)?\s*\d+\s*\.\s*\d+(?:\s*\.\s*\d+)?")


def resolve_solc_version(versions: List[str]) -> Tuple[int, int]:
    if not versions:
        return (4, MAX_PATCH)

    def highest_possible(version: str):
        vs = single_version_re.findall(version)
        if len(vs) > 1:
            return resolve_solc_version(vs)

        [version] = vs
        version = version.replace(" ", "")

        parts = version.split(".")
        if len(parts) == 3:
            [maj, min_, patch] = parts
        elif len(parts) == 2:
            [maj, min_, patch] = parts + [0]
        else:
            raise ValueError(f"Tried unpacking: {version}") from None

        min_ = int(min_)
        patch = int(patch)
        if min_ not in [4, 5, 6]:
            min_ = MAX_MIN

        if maj.startswith("^"):
            return (min_, MAX_PATCH)
        elif maj.startswith(">"):
            return (MAX_MIN, MAX_PATCH)
        elif maj.startswith("<="):
            return (min_, patch)
        elif maj.startswith("<"):
            if patch == 0:
                return (min_ - 1, MAX_PATCH)
            else:
                return (min_ - 1, patch - 1)
        else:
            return (min_, patch)

    candidates = []
    for ver in versions:
        try:
            candidates.append(highest_possible(ver))
        except (ValueError, AssertionError) as e:
            raise ValueError(f"ERROR: {ver} | {e}") from None

    return min(candidates or [(4, MAX_PATCH)])


_tests = [
    ([">=0.5.1 <0.6.0"], (5, MAX_PATCH)),
    (["^0.5.2", "^0.5.2", ">= 0.5.0"], (5, MAX_PATCH)),
    (["^ 0.4 .9"], (4, MAX_PATCH)),
    (["0.4.25", "0.4.25", ">= 0.4.1 < 0.5"], (4, 25)),
    (['"0.4.24"'], (4, 24)),
    (["^0.5.0 <6.0.0"], (5, MAX_PATCH)),
    ([">=0.4.1 <=0.4.20"], (4, 20)),
]

for t_in, t_out in _tests:
    try:
        assert (x := resolve_solc_version(t_in)) == t_out, f"{t_in} -> {x} != {t_out}"
    except ValueError:
        print(t_in)
        raise

MIGRATIONS_FILE = (
    Path(__file__).parent / "../example/crowdsale/build/contracts/Migrations.json"
).resolve()

TRUFFLE_CONFIG_CONTENTS_FMT = """module.exports = {{
  networks: {{
    development: {{
      host: "127.0.0.1",
      port: 8545,
      network_id: "*",
      gas: 1000000000
    }}
  }},
  compilers: {{
    solc: {{
      version: "{version}",
    }}
  }}
}};"""

TRUFFLE_MIGRATIONS_CONTENTS = """var Migrations = artifacts.require("Migrations");

module.exports = function(deployer) {
  deployer.deploy(Migrations);
};"""

TRUFFLE_DEPLOY_CONTENTS_FMT = """/* AUTO GENERATED */
{declarations}

module.exports = function(deployer) {{
{calls}
}};"""
REQUIRE_LINE_FMT = 'var {var_name} = artifacts.require("{artifact}");'
DEPLOY_LINE_FMT = "deployer.deploy({var_name});"


def truffle_deploy_generate(contracts: List[str]) -> str:
    declarations = [
        REQUIRE_LINE_FMT.format(var_name=contract, artifact=contract)
        for contract in contracts
    ]
    calls = [DEPLOY_LINE_FMT.format(var_name=contract) for contract in contracts]

    return TRUFFLE_DEPLOY_CONTENTS_FMT.format(
        declarations="\n".join(declarations), calls="\n".join("  " + c for c in calls)
    )


def prep():
    solc_versions = [
        "0.4.10",
        "0.4.13",
        "0.4.16",
        "0.4.19",
        "0.4.22",
        "0.4.25",
        "0.4.6",
        "0.5.0",
        "0.5.16",
        "0.5.4",
        "0.5.7",
        "0.6.0",
        "0.4.11",
        "0.4.14",
        "0.4.17",
        "0.4.20",
        "0.4.23",
        "0.4.26",
        "0.4.8",
        "0.5.1",
        "0.5.2",
        "0.5.5",
        "0.5.8",
        "0.6.11",
        "0.4.12",
        "0.4.15",
        "0.4.18",
        "0.4.21",
        "0.4.24",
        "0.4.4",
        "0.4.9",
        "0.5.10",
        "0.5.3",
        "0.5.6",
        "0.5.9",
    ]

    for v in solc_versions:
        subprocess.call(f"solc-select install {v}".split())


if __name__ == "__main__":
    main(args.directory, args.output)


from contextlib import contextmanager
from pathlib import Path
import json

@contextmanager
def progress_save(*argbindings, **kwbindings):
    # Code to acquire resource, e.g.:
    backup_fmt = "/tmp/ilf_{}_progress.json".format

    kwbindings = {
        k: ((v, None) if not isinstance(v, (tuple, list)) else v)
        for k, v in kwbindings.items()
    }
    bindings = list(argbindings) + [
        (name, ser, deser) for (name, (ser, deser)) in kwbindings.items()
    ]
    assert all(map(lambda t: len(t) == 3, bindings))
    refs = []
    for (name, deserialize, _) in bindings:
        log_file = Path(backup_fmt(name))

        deserialize = deserialize or (lambda x: x)
        if log_file.exists():
            refs.append(deserialize(json.load(log_file.open())))
        else:
            refs.append(deserialize())

    try:
        yield tuple(refs)
    finally:
        # Code to release resource, e.g.:
        for r, (name, _, serialize) in zip(refs, bindings):
            log_file = Path(backup_fmt(name))

            serialize = serialize or (lambda x: x)
            json.dump(serialize(r), log_file.open("w"))


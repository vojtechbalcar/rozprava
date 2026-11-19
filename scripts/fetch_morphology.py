"""Download the Czech morphology model that the ingest job uses to index word forms.

MorphoDiTa's MorfFlex CZ 2.1 + PDT-C 2.0 model (ÚFAL MFF UK) is distributed under
CC BY-NC-SA 4.0 from the LINDAT/CLARIAH-CZ repository: hdl.handle.net/11234/1-5985.
The archive is about 103 MB; only the tagger (26 MB, which includes the dictionary),
README and LICENSE are kept, under <data dir>/models/. The archive digest is checked.

Usage: uv run python scripts/fetch_morphology.py
"""

import hashlib
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from rozprava.morphology import MODEL, model_path
from rozprava.settings import get_settings

URL = (
    "https://lindat.mff.cuni.cz/repository/server/api/core/bitstreams/handle/11234/1-5985/"
    f"{MODEL}.zip"
)
SHA256 = "4dcc33862cd4a2919c1079cd843d0e68b8ebbe01ea8895bb02179805e03774e7"
KEEP = (f"{MODEL}.tagger", "README", "LICENSE")
USER_AGENT = "Rozprava (https://github.com/vojtechbalcar/rozprava)"


def main() -> int:
    target = model_path(get_settings().data_dir)
    if target.is_file():
        print(f"Already present: {target}")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "model.zip"
        request = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
        print(f"Downloading {URL}")
        with urllib.request.urlopen(request, timeout=120) as response, archive.open("wb") as out:
            shutil.copyfileobj(response, out)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != SHA256:
            print(f"Unexpected SHA-256 {digest}; nothing was installed.", file=sys.stderr)
            return 1
        with zipfile.ZipFile(archive) as zf:
            for name in KEEP:
                # Read named members only; never extract arbitrary archive paths.
                data = zf.read(f"{MODEL}/{name}")
                partial = target.parent / f".{name}.part"
                partial.write_bytes(data)
                partial.replace(target.parent / name)
    print(f"Installed {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""_pf2: backend registry (#6/#9), release attestation (#4), telemetry NPU dump."""

import ast
import json
import pathlib
import re
import subprocess
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG = []


def log(m):
    LOG.append(str(m))
    print(m, flush=True)


def patch(path, fn, label):
    p = ROOT / path
    try:
        text = p.read_text(encoding="utf-8")
        new = fn(text)
        if new is None:
            log(f"SKIP {label}: anchor not found")
        elif new == text:
            log(f"SKIP {label}: already applied")
        else:
            p.write_text(new, encoding="utf-8", newline="\n")
            log(f"OK   {label}")
    except Exception as e:
        log(f"FAIL {label}: {e}\n{traceback.format_exc()}")


def registry(text):
    if "openvino_genai" in text:
        return text
    new = text.replace("    openvino,\n", "    openvino,\n    openvino_genai,\n", 1)
    new = new.replace("    llama_cpp,\n", "    lemonade,\n    llama_cpp,\n", 1)
    new = new.replace(
        '    "openvino": openvino,\n',
        '    "openvino": openvino,\n'
        '    "openvino_genai": openvino_genai,\n'
        '    "lemonade": lemonade,\n',
        1,
    )
    if "openvino_genai" not in new or '"lemonade"' not in new:
        raise RuntimeError("one or more registry anchors not found")
    return new


def attest_pin():
    try:
        raw = subprocess.run(
            ["gh", "api", "repos/actions/attest-build-provenance/tags", "--paginate", "--slurp"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if raw.returncode != 0:
            log(f"WARN pin fetch rc={raw.returncode}: {raw.stderr[:200]}")
            return None
        pages = json.loads(raw.stdout)
        tags = []
        for page in pages if isinstance(pages, list) else []:
            if isinstance(page, list):
                tags.extend(page)
            elif isinstance(page, dict):
                tags.append(page)
        for t in tags:
            if t.get("tag_name") == "v4.2.2":
                return t.get("commit", {}).get("sha")
    except Exception as e:
        log(f"WARN pin fetch: {e}")
    return None


PERMS_RE = re.compile(
    r"(  build:\n    name: Build, checksum, SBOM\n    runs-on: ubuntu-latest\n)(    steps:)"
)


def release_yaml(text):
    if "attest-build-provenance" in text:
        return text
    sha = attest_pin()
    if not sha:
        raise RuntimeError("could not resolve pinned SHA for attest-build-provenance v4.2.2")
    new, n = PERMS_RE.subn(
        r"\1    permissions:\n      contents: read\n      id-token: write\n"
        r"      attestations: write\n\2",
        text,
        1,
    )
    if n != 1:
        raise RuntimeError("build-job anchor not found")
    new = new.replace(
        "      - name: Upload artifacts",
        "      - name: Attest build provenance\n"
        f"        uses: actions/attest-build-provenance@{sha}  # v4.2.2\n"
        "        with:\n"
        "          subject-path: dist/*\n"
        "\n"
        "      - name: Upload artifacts",
        1,
    )
    if "attest-build-provenance" not in new:
        raise RuntimeError("upload-artifacts anchor not found")
    return new


log("== _pf2: registry + attestation + telemetry dump ==")
patch("aihwbench/backends/__init__.py", registry, "backends.registry-genai-lemonade")
patch(".github/workflows/release.yml", release_yaml, "release.attestation")

for mod in (
    "aihwbench/npu.py",
    "aihwbench/formal_schema.py",
    "aihwbench/backends/capabilities.py",
    "aihwbench/backends/lemonade.py",
    "aihwbench/backends/openvino_genai.py",
    "aihwbench/analysis/thermal.py",
    "aihwbench/export.py",
    "aihwbench/cli/dataset.py",
    "aihwbench/backends/__init__.py",
):
    p = ROOT / mod
    try:
        ast.parse(p.read_text(encoding="utf-8"))
        log(f"PARSE OK {mod}")
    except Exception as e:
        log(f"PARSE FAIL {mod}: {e}")

t = (ROOT / "aihwbench" / "telemetry.py").read_text(encoding="utf-8")
for name in ("summary", "provenance"):
    m = re.search(rf"    def {name}\(self\).*?(?=\n    def |\nclass |\Z)", t, re.S)
    log(f"TELEMETRY {name}():\n{(m.group(0) if m else 'NOT FOUND')}")

(ROOT / "scripts" / "_patch_log.txt").write_text("\n".join(LOG) + "\n", encoding="utf-8")

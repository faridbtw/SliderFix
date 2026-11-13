#!/usr/bin/env python3
"""Build a companion handler JAR and unsigned resource overlay from local inputs."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent
METHOD = re.compile(
    r"(?m)^\.method public handleKeyEvent\(Landroid/view/KeyEvent;\)"
    r"Landroid/view/KeyEvent;\s*\n.*?^\.end method\s*$", re.S | re.M
)


def canonical(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def run(*args, env=None):
    subprocess.run([str(a) for a in args], check=True, env=env)


def build(args):
    # Reject inputs before creating output; never overwrite an existing build.
    for p in [args.keyhandler, args.framework_res, args.apktool]:
        if not p.is_file():
            raise SystemExit(f"Missing input: {p}")
    aapt = args.build_tools / "aapt2"
    if not aapt.is_file():
        raise SystemExit(f"Missing Android SDK tool: {aapt}")
    if args.out.exists():
        raise SystemExit("Output directory already exists; choose a new --out")
    args.out.mkdir(parents=True)
    scratch = args.out / ".work"
    scratch.mkdir()
    decoded = scratch / "keyhandler"
    run(args.java, "-jar", args.apktool, "d", "-r", "-f", args.keyhandler,
        "-o", decoded)
    candidates = list(decoded.glob(
        "smali*/org/lineageos/settings/device/KeyHandler.smali"))
    if len(candidates) != 1:
        raise SystemExit("Expected exactly one Lineage KeyHandler class")
    path = candidates[0]
    text = path.read_text()
    matches = list(METHOD.finditer(text))
    if len(matches) != 1:
        raise SystemExit("Expected exactly one handleKeyEvent method")
    match = matches[0]
    expected = (ROOT / "patches/handleKeyEvent-original.smali").read_text()
    if canonical(match.group()) != canonical(expected):
        raise SystemExit("Unrecognized handler implementation; inspect before porting")
    replacement = (ROOT / "patches/handleKeyEvent-patched.smali").read_text().rstrip()
    path.write_text(text[:match.start()] + replacement + "\n" + text[match.end():])
    unsigned = scratch / "handler-unsigned.apk"
    run(args.java, "-jar", args.apktool, "b", decoded, "-o", unsigned)
    jar = args.out / "nimarko-slider.jar"
    with zipfile.ZipFile(unsigned) as src, zipfile.ZipFile(
            jar, "w", zipfile.ZIP_DEFLATED) as dst:
        dex = [n for n in src.namelist() if re.fullmatch(r"classes\d*\.dex", n)]
        if not dex:
            raise SystemExit("Rebuilt handler has no DEX files")
        for name in dex:
            dst.writestr(name, src.read(name))
    resources = scratch / "overlay-res.zip"
    run(aapt, "compile", "--dir", ROOT / "overlay/res", "-o", resources)
    overlay = args.out / "NimarkoSliderOverlay-unsigned.apk"
    run(aapt, "link", "-o", overlay, "--manifest", ROOT / "overlay/AndroidManifest.xml",
        "-I", args.framework_res, resources)
    for p in [jar, overlay]:
        with zipfile.ZipFile(p) as archive:
            if archive.testzip() is not None:
                raise SystemExit(f"Invalid output archive: {p.name}")
    shutil.rmtree(scratch)
    print(f"Built {jar.name} and {overlay.name} in {args.out}")
    print("Sign the overlay before including it in a ROM. No device was contacted.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keyhandler", required=True, type=Path)
    parser.add_argument("--framework-res", required=True, type=Path)
    parser.add_argument("--apktool", required=True, type=Path)
    parser.add_argument("--build-tools", required=True, type=Path)
    parser.add_argument("--java", default="java")
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args()
    # Child tools receive absolute paths, so working-directory changes are harmless.
    for field in ["keyhandler", "framework_res", "apktool", "build_tools", "out"]:
        setattr(args, field, getattr(args, field).resolve())
    build(args)


if __name__ == "__main__":
    main()

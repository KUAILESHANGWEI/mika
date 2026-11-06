#!/usr/bin/env python3
"""Maintain the independent repository without deleting previously archived data."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

UPSTREAM = "wangzan101/Mika"
DESTINATION = "KUAILESHANGWEI/mika"
SCRIPT = ".github/scripts/mika_mirror.py"
WORKFLOW = ".github/workflows/mika-mirror.yml"
SIGNING_MARKER = "// Independent mirror signing"
SIGNING = '''
// Independent mirror signing. The persistent key is supplied by Actions secrets.
android {
    val mirrorStore = System.getenv("MIKA_KEYSTORE_PATH")
    if (!mirrorStore.isNullOrBlank()) {
        signingConfigs {
            create("mirror") {
                storeFile = file(mirrorStore)
                storeType = "PKCS12"
                storePassword = System.getenv("MIKA_KEYSTORE_PASSWORD")
                keyAlias = "mika"
                keyPassword = System.getenv("MIKA_KEYSTORE_PASSWORD")
            }
        }
        buildTypes.getByName("release").signingConfig = signingConfigs.getByName("mirror")
    }
}
'''


def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def api(path):
    return json.loads(run("gh", "api", path))


def releases():
    pages = json.loads(run("gh", "api", "--paginate", "--slurp",
                           f"repos/{DESTINATION}/releases?per_page=100"))
    return [release for page in pages for release in page]


def localize():
    # Work from Git's tracked paths, so binaries and private local files stay intact.
    paths = run("git", "ls-files", "-z").split("\0")
    for name in paths:
        if not name or name in (SCRIPT, WORKFLOW, "MIRROR.md"):
            continue
        path = Path(name)
        if not path.is_file() or path.is_symlink():
            continue
        raw = path.read_bytes()
        if b"\0" in raw:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        updated = re.sub(
            r"(github\.com/(?:repos/)?|raw\.githubusercontent\.com/|cdn\.jsdelivr\.net/gh/|"
            r"img\.shields\.io/github/(?:stars/|downloads/|v/release/)|[?&#]repos?=|star-history\.com/#)"
            r"wangzan101/mika(?=[/.\s?#&\"'<),`]|$)",
            lambda match: match.group(1) + DESTINATION, text, flags=re.I,
        )
        if updated != text:
            path.write_text(updated)
    gradle = Path("app/build.gradle.kts")
    text = gradle.read_text()
    if SIGNING_MARKER not in text:
        gradle.write_text(text + SIGNING)
    # Fail if a runtime/download reference escaped the transformation.
    links = Path("app/src/main/java/com/wangzan101/mika/about/MikaLinks.kt").read_text()
    if f'https://api.github.com/repos/{DESTINATION}/releases/latest' not in links:
        raise RuntimeError("Update API is not localized")


def digest_file(path):
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(chunk)
    return "sha256:" + sha.hexdigest()


def archive_release(release):
    tag = release["tag_name"]
    archive_tag = "upstream-" + tag
    saved_releases = releases()
    existing = next((item for item in saved_releases if item["tag_name"] == archive_tag), None)
    if existing is None:
        run("gh", "release", "create", archive_tag, "--repo", DESTINATION,
            "--target", run("git", "rev-parse", tag), "--draft", "--prerelease",
            "--title", "Upstream archive " + tag,
            "--notes", "Original upstream assets, preserved independently. Install the localized APK from the latest stable release for this repository's update service.")
        existing = next(item for item in releases()
                        if item["tag_name"] == archive_tag)
    saved = {asset["name"]: asset for asset in existing["assets"]}
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        for asset in release["assets"]:
            name = asset["name"]
            if Path(name).name != name or name in (".", ".."):
                raise RuntimeError("Unsafe asset name")
            old = saved.get(name)
            if old and old["size"] == asset["size"] and asset.get("digest") and old.get("digest") == asset["digest"]:
                continue
            path = folder / name
            with path.open("wb") as output:
                subprocess.run(["gh", "api", f'repos/{UPSTREAM}/releases/assets/{asset["id"]}',
                                "-H", "Accept: application/octet-stream"], stdout=output, check=True)
            if path.stat().st_size != asset["size"]:
                raise RuntimeError("Incomplete download: " + name)
            if asset.get("digest") and digest_file(path) != asset["digest"]:
                raise RuntimeError("Digest mismatch: " + name)
            # Preserve earlier bytes if upstream replaces an asset in place.
            if old:
                previous = folder / ("previous-" + name)
                with previous.open("wb") as output:
                    subprocess.run(["gh", "api", f'repos/{DESTINATION}/releases/assets/{old["id"]}',
                                    "-H", "Accept: application/octet-stream"], stdout=output, check=True)
                if previous.stat().st_size != old["size"] or (old.get("digest") and digest_file(previous) != old["digest"]):
                    raise RuntimeError("Cannot preserve previous asset: " + name)
                versioned = folder / ("revision-" + digest_file(previous)[7:19] + "-" + name)
                previous.rename(versioned)
                run("gh", "release", "upload", archive_tag, str(versioned), "--repo", DESTINATION, "--clobber")
            run("gh", "release", "upload", archive_tag, str(path), "--repo", DESTINATION, "--clobber")
        metadata = folder / "upstream-release.json"
        metadata.write_text(json.dumps(release, ensure_ascii=False, indent=2) + "\n")
        run("gh", "release", "upload", archive_tag, str(metadata), "--repo", DESTINATION, "--clobber")
    run("gh", "release", "edit", archive_tag, "--repo", DESTINATION, "--draft=false", "--prerelease", "--latest=false")
    verified = api(f"repos/{DESTINATION}/releases/tags/{archive_tag}")
    assets = {a["name"]: a for a in verified["assets"]}
    for source in release["assets"]:
        archived = assets[source["name"]]
        if archived["size"] != source["size"] or (source.get("digest") and archived.get("digest") != source["digest"]):
            raise RuntimeError("Archive verification failed: " + source["name"])
    return tag


def sync():
    run("git", "config", "user.name", "github-actions[bot]")
    run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    remote = "https://github.com/" + UPSTREAM + ".git"
    if "upstream" not in run("git", "remote").splitlines():
        run("git", "remote", "add", "upstream", remote)
    # A missing upstream never removes the independent repository or saved assets.
    fetch = subprocess.run(["git", "fetch", "upstream", "+refs/heads/*:refs/remotes/upstream/*", "--tags"])
    if fetch.returncode == 0:
        merged = subprocess.run(["git", "merge", "--no-commit", "--no-ff", "-X", "theirs", "upstream/main"])
        if merged.returncode:
            subprocess.run(["git", "merge", "--abort"], check=True)
            raise RuntimeError("Upstream merge needs review, existing published state preserved")
        localize()
        run("git", "add", "-A")
        run("git", "diff", "--cached", "--check")
        if Path(".git/MERGE_HEAD").exists() or run("git", "status", "--porcelain"):
            run("git", "commit", "-m", "Sync upstream and retain independent download/update URLs")
        # GitHub disables scheduled workflows after 60 days without repository activity.
        if time.time() - int(run("git", "log", "-1", "--format=%ct")) > 30 * 86400:
            run("git", "commit", "--allow-empty", "-m", "Keep the scheduled independent mirror active")
        run("git", "push", "origin", "HEAD:main")
        refs = run("git", "for-each-ref", "--format=%(refname)", "refs/remotes/upstream").splitlines()
        mappings = ["+" + ref + ":refs/heads/upstream/" + ref.removeprefix("refs/remotes/upstream/")
                    for ref in refs if not ref.endswith("/HEAD")]
        run("git", "push", "origin", *mappings, "--tags")
    else:
        print("::warning::Upstream unavailable. Existing code and releases are retained.")
    # Only API unavailability falls back. An incomplete asset archive must fail visibly.
    try:
        release = api(f"repos/{UPSTREAM}/releases/latest")
    except subprocess.CalledProcessError:
        print("::warning::Upstream release API unavailable. Using the saved archive if needed.")
        saved = releases()
        archived = next((r for r in saved if r["tag_name"].startswith("upstream-v") and not r["draft"]), None)
        tag = archived["tag_name"].removeprefix("upstream-") if archived else ""
    else:
        tag = archive_release(release)
    stable = releases()
    complete = next((r for r in stable if r["tag_name"] == tag + "+mirror" and not r["draft"] and not r["prerelease"]
                     and any(a["name"] == "SHA256SUMS" for a in r["assets"])), None)
    needs_build = bool(tag and not complete)
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as output:
        output.write(f"tag={tag}\nbuild={'true' if needs_build else 'false'}\n")
    print(json.dumps({"release": tag, "build": needs_build}))


if __name__ == "__main__":
    {"localize": localize, "sync": sync}[sys.argv[1]]()

"""Download the latest KipHakkhoSutgi ODS from stti.moe.edu.tw and convert it.

Flow:
1. Scrape the download page to find the current ODS link (the filename is
   dated, e.g. ttg_20241219.ods, and changes with each release).
2. Download it to a temp dir and compare its SHA256 against public/manifest.json.
3. On change, create public/{YYYYMMDD-HHMM}/, store the original under
   tangloo/ (gitignored) and convert it to bunji/ CSV + JSON.
"""

import datetime
import hashlib
import html
import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests

try:
    from convert_KipHakkhoSutgiData import convert_KipHakkhoSutgiData
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from convert_KipHakkhoSutgiData import convert_KipHakkhoSutgiData

SITE = "https://stti.moe.edu.tw"
URL_DOWNLOAD_PAGE = f"{SITE}/file-download/newsData/?lang=sutgi"
USER_AGENT = "Mozilla/5.0 (KipHakkhoSutgiDataMirror; +https://github.com/ChhoeTaigi/KipHakkhoSutgiDataMirror)"

BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"
MANIFEST_FILE = PUBLIC_DIR / "manifest.json"

LOCAL_ODS_NAME = "KipHakkhoSutgiData.ods"


def get_timestamp_dir():
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    return PUBLIC_DIR / timestamp


def find_ods_url():
    """Return (absolute_url, filename) of the ODS linked from the download page."""
    print(f"Fetching download page {URL_DOWNLOAD_PAGE}...")
    r = requests.get(URL_DOWNLOAD_PAGE, headers={"User-Agent": USER_AGENT}, timeout=60)
    r.raise_for_status()
    links = re.findall(r'href="([^"]+\.ods)"', r.text, flags=re.I)
    if not links:
        raise RuntimeError("No .ods link found on the download page")
    if len(links) > 1:
        print(f"Warning: multiple .ods links found, using the first: {links}")
    url = urljoin(SITE, html.unescape(links[0]))
    return url, os.path.basename(url)


def download_file(url, target_path):
    print(f"Downloading {url} to {target_path}...")
    with requests.get(url, stream=True, headers={"User-Agent": USER_AGENT}, timeout=120) as r:
        r.raise_for_status()
        with open(target_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
    print(f"Downloaded {target_path.stat().st_size / 1024:.1f} KB")


def calculate_file_hash(filepath):
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            sha256.update(block)
    return sha256.hexdigest()


def load_manifest():
    if MANIFEST_FILE.exists():
        with open(MANIFEST_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_manifest(data):
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main():
    print("Starting update check...")
    temp_dir = PUBLIC_DIR / "temp_update"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        ods_url, source_name = find_ods_url()
        temp_ods = temp_dir / LOCAL_ODS_NAME
        download_file(ods_url, temp_ods)
        new_hash = calculate_file_hash(temp_ods)

        manifest = load_manifest()
        old_hash = manifest.get("files", {}).get(LOCAL_ODS_NAME)
        target_dir = None

        if old_hash == new_hash:
            print("No changes detected.")
            latest = manifest.get("latest_version_dir")
            if latest and (PUBLIC_DIR / latest).exists():
                target_dir = PUBLIC_DIR / latest
                print(f"Using existing latest directory: {target_dir}")
            else:
                print("Latest version directory missing. Creating a new one.")
        else:
            print("Change detected." if old_hash else "No existing manifest. Initial import.")

        if target_dir is None:
            target_dir = get_timestamp_dir()
            tangloo_dir = target_dir / "tangloo"
            tangloo_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(temp_ods), str(tangloo_dir / LOCAL_ODS_NAME))
            print(f"Created version directory: {target_dir}")

            save_manifest({
                "last_updated": datetime.datetime.now().isoformat(),
                "latest_version_dir": target_dir.name,
                "source": {LOCAL_ODS_NAME: {"url": ods_url, "filename": source_name}},
                "files": {LOCAL_ODS_NAME: new_hash},
            })
            print("Updated manifest.json.")

        tangloo_ods = target_dir / "tangloo" / LOCAL_ODS_NAME
        if not tangloo_ods.exists():
            # The original is gitignored, so a fresh clone may lack it; reuse the download.
            tangloo_ods.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(temp_ods), str(tangloo_ods))

        bunji_dir = target_dir / "bunji"
        bunji_dir.mkdir(parents=True, exist_ok=True)
        convert_KipHakkhoSutgiData(
            str(tangloo_ods),
            str(bunji_dir / "KipHakkhoSutgiData.csv"),
            str(bunji_dir / "KipHakkhoSutgiData.json"),
        )
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    print("\nUpdate complete!")
    print(f"Data stored in: {target_dir}")


if __name__ == "__main__":
    main()

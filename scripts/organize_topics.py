#!/usr/bin/env python3
"""Put links to each session's source files in one topic folder."""
import json
import os
import re
import subprocess
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOPICS = ROOT / "topics"


def slug(title):
    text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def link(folder, name, source):
    target = folder / name
    relative = os.path.relpath(ROOT / source, folder)
    if target.is_symlink():
        target.unlink()
    elif target.exists():
        raise FileExistsError(f"Refusing to replace {target}")
    target.symlink_to(relative)


def main():
    archive = json.loads((ROOT / "data/notion-records.json").read_text())
    attachments = json.loads((ROOT / "data/attachments.json").read_text())
    videos = json.loads((ROOT / "transcripts/manifest.json").read_text())
    rows = {row["id"]: row for row in archive["records"]}
    view = archive["views"]["3cecf2ed-4c85-81d7-a3e9-000c790251a8"]
    named_rows = [rows[row_id] for row_id in view["page_sort"] if row_id in rows and rows[row_id]["title"].strip()]
    slide_by_row = {}
    closing_slide = None
    for file in attachments:
        if not file["downloaded"] or not file["name"].endswith(".pdf"):
            continue
        if file["name"] == "5050__Getting_Great.pdf":
            closing_slide = file["path"]
        else:
            slide_by_row[file["page_id"]] = file["path"]
    by_session = {}
    for video in videos:
        for session in video["sessions"]:
            by_session.setdefault(session, {})[video["type"]] = video

    TOPICS.mkdir(exist_ok=True)
    lines = ["# C9 topics", "", "Each topic folder brings its C9 recording transcript and slide deck together.",
             "Links point to the original archived files; the files are not duplicated.",
             "Older cohort reference transcripts are included where the Content page links them, even when the video topic differs.",
             "", "| Topic | C9 recording transcript | Slides | Older reference transcript |",
             "| --- | --- | --- | --- |"]
    for row in named_rows:
        title = row["title"]
        folder_name = slug(title)
        sources = by_session.get(title, {})
        slide = closing_slide if title.startswith("Closing (") else slide_by_row.get(row["id"])
        if sources or slide:
            folder = TOPICS / folder_name
            folder.mkdir(exist_ok=True)
            for kind, prefix in (("c9", "recording"), ("reference", "reference")):
                if kind in sources:
                    for ext, key in (("md", "text_path"), ("json", "raw_path")):
                        link(folder, f"{prefix}.{ext}", sources[kind][key])
            if slide:
                link(folder, "slides.pdf", slide)
                subprocess.run(["pdftotext", "-layout", "-nopgbrk", str(folder / "slides.pdf"),
                                str(folder / "slides.txt")], check=True)
                if not (folder / "slides.txt").stat().st_size:
                    (folder / "slides.txt").unlink()
            label = f"[{title}]({folder_name}/)"
        else:
            label = title
        recording = f"[transcript]({folder_name}/recording.md)" if "c9" in sources else "—"
        slides = f"[PDF]({folder_name}/slides.pdf)" if slide else "—"
        reference = f"[transcript]({folder_name}/reference.md)" if "reference" in sources else "—"
        lines.append(f"| {label} | {recording} | {slides} | {reference} |")
    lines += ["", "Slide PDFs with embedded text also have a `slides.txt` beside them. The Resilience deck is image-only, so its text was not extractable.",
              "The Getting Great deck is filed with Closing based on its title; Notion attached it to the Resilience row.",
              "Reference links for Building an AI first organization, Selling, Storytelling, and Fundraising mechanics point to videos on different topics.",
              "", "Run `python3 scripts/organize_topics.py` after refreshing source files.", ""]
    (TOPICS / "README.md").write_text("\n".join(lines))
    print(f"Organized {len(named_rows)} topics; {sum(bool(by_session.get(row['title'], {}).get('c9') and (closing_slide if row['title'].startswith('Closing (') else slide_by_row.get(row['id']))) for row in named_rows)} recording/slide pairs")


if __name__ == "__main__":
    main()

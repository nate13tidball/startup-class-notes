#!/usr/bin/env python3
"""Extract slide text and OCR sparse pages into lecture-organized Markdown and JSON."""
import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from rapidocr import RapidOCR

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "lectures"
VIEW = "3cecf2ed-4c85-81d7-a3e9-000c790251a8"
GETTING_GREAT_ROW = "3e9cf2ed-4c85-82ea-ad07-8137772d330b"

RESILIENCE_VISUALS = [
    "50/50 title slide.",
    "Photographs of Hillary Allen running and with a bicycle.",
    "Childhood science photograph and later scientist portrait.",
    "Mountain running and race photographs.",
    "Mountain running and race photographs.",
    "Mountain running and race photographs.",
    "Mountain running and race photographs.",
    "Emergency response on rocky terrain.",
    "Photographs of bandaged legs.",
    "Hospital recovery photographs.",
    "Assisted travel and stair climbing.",
    "Rehabilitation in a pool and with a mobility device.",
    "Return to running photographs.",
    "Race finish photograph.",
    "Climbing rugged terrain.",
    "Flag and medal photograph.",
    "Running photograph.",
    "Group photograph.",
    "Leg and ankle X-ray images.",
    "Cycling photograph.",
    "50/50 closing slide.",
]


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def video_id(url):
    parsed = urlparse(url)
    if parsed.hostname in ("youtu.be", "www.youtu.be"):
        return parsed.path.strip("/")
    if "youtube.com" in (parsed.hostname or ""):
        return parse_qs(parsed.query).get("v", [""])[0]
    return ""


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def text_block(value):
    return "````text\n" + value.rstrip() + "\n````\n"


def main():
    notion = json.loads((DATA / "notion-records.json").read_text())
    records = {row["id"]: row for row in notion["records"]}
    ids = notion["views"][VIEW]["page_sort"]
    attachments = json.loads((DATA / "attachments.json").read_text())
    videos = {video_id(v["url"]): v for v in json.loads((DATA / "youtube.json").read_text())}
    pdfs = [a for a in attachments if a.get("downloaded") and a["name"].lower().endswith(".pdf")]
    by_row = {}
    for attachment in pdfs:
        row_id = GETTING_GREAT_ROW if attachment["name"] == "5050__Getting_Great.pdf" else attachment["page_id"]
        by_row.setdefault(row_id, []).append(attachment)
    OUT.mkdir(exist_ok=True)
    ocr = RapidOCR()
    all_decks = []
    index = ["# C9 lectures and slide transcripts", "", "Slides are grouped by their matching C9 lecture row. Text marked OCR may contain recognition errors. Visual-only slides retain a page link to the original PDF.", ""]
    for row_id in ids:
        row = records.get(row_id)
        if not row or not row["title"].strip():
            continue
        title = row["title"]
        recording = row["properties"].get("oCdi", "")
        match = videos.get(video_id(recording), {})
        folder = OUT / slug(title)
        folder.mkdir(exist_ok=True)
        decks = by_row.get(row_id, [])
        index.append(f"## {title}")
        index.append("")
        index.append(f"[Notion lecture row](https://fiftyyears.notion.site/{row_id.replace('-', '')})")
        if recording:
            index.append(f"Recording: [{match.get('title', 'C9 recording')}]({recording})")
        if not decks:
            index.extend(["", "No PDF slides were attached to this lecture row.", ""])
            continue
        index.append("")
        for attachment in decks:
            pdf = ROOT / attachment["path"]
            pages = int(re.search(r"^Pages:\s+(\d+)", command("pdfinfo", str(pdf)), re.M).group(1))
            extracted = command("pdftotext", "-layout", str(pdf), "-").split("\f")
            if len(extracted) < pages:
                raise RuntimeError(f"Expected {pages} text pages for {pdf}, found {len(extracted)}")
            deck_slug = slug(pdf.stem)
            dest = folder / f"{deck_slug}.md"
            pdf_link = f"../../../{attachment['path']}"
            note = ("This PDF was attached under Resilience with Hillary Allen in Notion. Its title and the Closing lecture name indicate it belongs here."
                    if attachment["page_id"] != row_id else "")
            lines = [f"# {title}: {pdf.stem.replace('_', ' ')}", "", f"Original PDF: [{pdf.name}]({pdf_link})", f"Source Notion row: [{title}](https://fiftyyears.notion.site/{row_id.replace('-', '')})"]
            if recording:
                lines.append(f"C9 recording: [{match.get('title', 'Recording')}]({recording})")
            if note:
                lines.append(f"Assignment note: {note}")
            lines.append("")
            deck = {"lecture": title, "lecture_row_id": row_id, "source_row_id": attachment["page_id"], "pdf": attachment["path"], "recording": recording, "recording_title": match.get("title", ""), "assignment_note": note, "slides": []}
            print(f"{title}: {pdf.name} ({pages} slides)", flush=True)
            for number in range(1, pages + 1):
                native = extracted[number - 1].strip()
                recognized = ""
                if len(native) < 40:
                    with tempfile.TemporaryDirectory(prefix="fifty-years-slide-") as tmp:
                        prefix = str(Path(tmp) / "page")
                        subprocess.run(["pdftoppm", "-f", str(number), "-l", str(number), "-singlefile", "-scale-to", "1400", "-png", str(pdf), prefix], check=True, capture_output=True)
                        result = ocr(prefix + ".png")
                        if result.txts:
                            recognized = "\n".join(result.txts).strip()
                visual = RESILIENCE_VISUALS[number - 1] if pdf.name == "Resilience_-_Hillary_Allen.pdf" else ""
                slide = {"page": number, "native_text": native, "ocr_text": recognized, "visual_note": visual}
                deck["slides"].append(slide)
                lines.extend([f"## Slide {number}", "", f"[View slide in original PDF]({pdf_link}#page={number})", ""])
                if native:
                    lines.extend(["Embedded text:", "", text_block(native), ""])
                if recognized:
                    lines.extend(["OCR text:", "", text_block(recognized), ""])
                if visual:
                    lines.extend([f"Visual note: {visual}", ""])
                elif not native and not recognized:
                    lines.extend(["Visual-only slide; see original PDF.", ""])
            dest.write_text("\n".join(lines))
            all_decks.append(deck)
            index.append(f"- [{pdf.name} — {pages} slides]({slug(title)}/{deck_slug}.md)")
            if note:
                index.append(f"  - {note}")
            print(f"  wrote {dest.relative_to(ROOT)}", flush=True)
        index.append("")
    (OUT / "README.md").write_text("\n".join(index))
    (OUT / "slides.json").write_text(json.dumps(all_decks, ensure_ascii=False, indent=2) + "\n")
    print(f"Finished {len(all_decks)} PDFs, {sum(len(d['slides']) for d in all_decks)} slides", flush=True)


if __name__ == "__main__":
    main()

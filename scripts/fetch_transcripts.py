#!/usr/bin/env python3
"""Save available YouTube captions for the archived C9 sessions and references."""
import json
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "transcripts"


def video_id(url):
    parsed = urlparse(url)
    if parsed.hostname in {"youtu.be", "www.youtu.be"}:
        return parsed.path.strip("/")
    if parsed.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        return parse_qs(parsed.query).get("v", [""])[0]
    return ""


def stamp(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def markdown(item, segments):
    lines = [f"# {item['video_title']}", "", f"Video: {item['url']}",
             f"Type: {item['type']}", f"Source: {item['source']}",
             "Sessions: " + "; ".join(item["sessions"]), ""]
    chunk, start = [], None
    for segment in segments:
        if start is None:
            start = segment["start"]
        if chunk and segment["start"] - start >= 30:
            lines.append(f"[{stamp(start)}] " + " ".join(chunk))
            lines.append("")
            chunk, start = [], segment["start"]
        chunk.append(re.sub(r"\s+", " ", segment["text"]).strip())
    if chunk:
        lines.append(f"[{stamp(start)}] " + " ".join(chunk))
        lines.append("")
    return "\n".join(lines)


def main():
    archive = json.loads((ROOT / "data/notion-records.json").read_text())
    metadata = {video_id(v["url"]): v for v in json.loads((ROOT / "data/youtube.json").read_text())}
    rows = {r["id"]: r for r in archive["records"]}
    view = archive["views"]["3cecf2ed-4c85-81d7-a3e9-000c790251a8"]
    videos = {}
    for row_id in view["page_sort"]:
        row = rows.get(row_id)
        if not row:
            continue
        for key, kind in (("oCdi", "c9"), ("fM`:", "reference")):
            url = row["properties"].get(key, "")
            vid = video_id(url)
            if not vid:
                continue
            item = videos.setdefault(vid, {"id": vid, "type": kind, "url": url,
                                           "video_title": metadata.get(vid, {}).get("title"),
                                           "source": "YouTube English captions",
                                           "sessions": []})
            if row["title"] not in item["sessions"]:
                item["sessions"].append(row["title"])
    OUT.mkdir(exist_ok=True)
    for vid, item in videos.items():
        folder = OUT / item["type"]
        folder.mkdir(exist_ok=True)
        raw = folder / f"{vid}.json"
        readable = folder / f"{vid}.md"
        item["raw_path"] = str(raw.relative_to(ROOT))
        item["text_path"] = str(readable.relative_to(ROOT))
        if vid == "-dwIVJokasc" and raw.exists():
            item["source"] = "local faster-whisper base.en transcription"
        if raw.exists():
            segments = json.loads(raw.read_text())
        else:
            for attempt in range(3):
                proc = subprocess.run(["youtube_transcript_api", "--format", "json", "--", vid],
                                      capture_output=True, text=True)
                try:
                    segments = json.loads(proc.stdout)[0] if proc.returncode == 0 else []
                except (ValueError, IndexError, TypeError):
                    segments = []
                if segments:
                    raw.write_text(json.dumps(segments, ensure_ascii=False, indent=2) + "\n")
                    break
                if attempt < 2:
                    time.sleep(2 ** attempt)
            else:
                item["status"] = "unavailable"
                item["error"] = (proc.stderr or proc.stdout).strip()[:500]
                print(f"{vid}: unavailable")
                continue
        item["status"] = "downloaded"
        item["segments"] = len(segments)
        readable.write_text(markdown(item, segments))
        print(f"{vid}: {len(segments)} segments")
        time.sleep(.5)
    for row_id in view["page_sort"]:
        row = rows.get(row_id)
        if not row:
            continue
        url = row["properties"].get("oCdi", "")
        if urlparse(url).hostname != "www.loom.com":
            continue
        vid = urlparse(url).path.rstrip("/").split("/")[-1]
        folder = OUT / "c9"
        raw, readable = folder / f"{vid}.json", folder / f"{vid}.md"
        item = {"id": vid, "type": "c9", "platform": "loom", "url": url,
                "video_title": row["title"], "source": "Loom published transcript", "sessions": [row["title"]],
                "raw_path": str(raw.relative_to(ROOT)), "text_path": str(readable.relative_to(ROOT))}
        try:
            if raw.exists():
                segments = json.loads(raw.read_text())
            else:
                page = urlopen(url, timeout=30).read().decode()
                match = re.search(r"window\.__APOLLO_STATE__ = (\{.*?\});", page, re.S)
                state = json.loads(match.group(1))
                transcript = next(v for k, v in state.items() if k.startswith("VideoTranscriptDetails:"))
                data = json.load(urlopen(transcript["source_url"], timeout=30))
                segments = [{"start": p["ts"], "text": p["value"]} for p in data["phrases"]]
                raw.write_text(json.dumps(segments, ensure_ascii=False, indent=2) + "\n")
            readable.write_text(markdown(item, segments))
            item.update({"status": "downloaded", "segments": len(segments)})
            print(f"{vid}: {len(segments)} segments (Loom)")
        except (OSError, ValueError, KeyError, AttributeError, StopIteration) as exc:
            item.update({"status": "unavailable", "error": str(exc)})
            print(f"{vid}: unavailable (Loom)")
        videos[vid] = item
    (OUT / "manifest.json").write_text(json.dumps(list(videos.values()), ensure_ascii=False, indent=2) + "\n")
    lines = ["# Lecture transcripts", "", "Transcript text is unedited and may contain transcription errors.",
             "YouTube files come from English captions, except Technoeconomics, which was transcribed locally from audio with faster-whisper base.en after YouTube returned HTTP 429. Milestones comes from Loom's published transcript.",
             "Each `.json` file preserves timestamped segments. Each `.md` file groups them into readable 30-second passages.",
             "", "## C9 recordings", "",
             "| Session | Video | Transcript |", "| --- | --- | --- |"]
    for item in videos.values():
        if item["type"] != "c9":
            continue
        title = (item["video_title"] or item["id"]).replace("|", "\\|")
        link = f"[read]({Path(item['text_path']).relative_to('transcripts')})" if item["status"] == "downloaded" else "Unavailable (YouTube HTTP 429)"
        lines.append(f"| {', '.join(item['sessions'])} | [{title}]({item['url']}) | {link} |")
    lines += ["", "## Older cohort references", "",
              "These links are preserved as attached to C9 rows. Some reference titles do not match their row topic.",
              "", "| C9 row | Video | Transcript |", "| --- | --- | --- |"]
    for item in videos.values():
        if item["type"] != "reference":
            continue
        title = (item["video_title"] or item["id"]).replace("|", "\\|")
        lines.append(f"| {', '.join(item['sessions'])} | [{title}]({item['url']}) | [read]({Path(item['text_path']).relative_to('transcripts')}) |")
    lines += ["", "Run `python3 scripts/fetch_transcripts.py` from the repository root to refresh missing transcripts.", ""]
    (OUT / "README.md").write_text("\n".join(lines))
    print(f"{sum(v['status'] == 'downloaded' for v in videos.values())}/{len(videos)} transcripts saved")


if __name__ == "__main__":
    main()

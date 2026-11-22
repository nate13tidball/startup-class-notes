# Fifty Years content archive

A local archive of the public Notion page [Content!](https://fiftyyears.notion.site/content-c9).

`python3 scripts/scrape.py` fetches the page's public Notion records, the database rows exposed by its embedded views, linked YouTube metadata via YouTube oEmbed, and downloadable presentation attachments. Output is saved in `data/` and `presentations/`.

`python3 scripts/scrape_more.py` also archives the C9 Humans directory and Startup Perks page. It skips the C9 calendar. The Humans archive is kept under ignored `data/c9-humans/` because it contains personal profile data. Contact imports are prepared outside the repository and sent only through the interaction-pipeline CLI.

The scraper uses Notion's public page endpoints and does not require account credentials. Some file links may expire; rerun the scraper to refresh them. Raw source records are preserved in `data/notion-records.json`; `data/content.md`, `data/youtube.json`, and `data/attachments.json` are convenient indexes.

## Lecture transcripts

See [`transcripts/README.md`](transcripts/README.md) for C9 recordings and older cohort references, linked to their source sessions. Each available transcript has a readable Markdown file and timestamped JSON segments. Run `python3 scripts/fetch_transcripts.py` to fetch new YouTube captions and the published Loom transcript; the script reuses files already downloaded. It requires the `youtube_transcript_api` CLI (`uv tool install youtube-transcript-api`).

Open [`topics/README.md`](topics/README.md) to browse recording transcripts and slide decks together by session. Topic folders link to the archived source files and include extracted slide text where available. Run `python3 scripts/organize_topics.py` after refreshing the archive or transcripts.

## Lecture slide content

[`data/lectures/README.md`](data/lectures/README.md) groups the downloaded PDF slides under their matching C9 lecture rows and links each slide back to its PDF page. Each deck has a Markdown transcript, and `data/lectures/slides.json` contains the same extracted text in structured form. Slides with little embedded text also have OCR; OCR may contain recognition errors. The entirely visual Resilience deck includes brief visual notes. The Getting Great PDF is grouped with Closing, although Notion attached it to the Resilience row.

To regenerate after downloading PDFs, install `rapidocr` and `onnxruntime` in a Python environment, ensure Poppler's `pdfinfo`, `pdftotext`, and `pdftoppm` are available, then run `python3 scripts/extract_slides.py` in that environment.

# Startup Class Notes

A topic-organized reference for learning how to start and build a business. The current collection comes from the public [Fifty Years 50/50 Content page](https://fiftyyears.notion.site/content-c9). This is an independent archive, not an official Fifty Years publication. The transcripts and slide text preserve source material and may contain transcription or OCR errors.

## Browse by topic

| Area | Class material |
| --- | --- |
| Choosing a problem | [What to build](topics/what-to-build/), [Sprinting the idea maze](topics/sprinting-the-idea-maze/) |
| Understanding customers | [Customer discovery](topics/customer-discovery-for-deep-tech-sf/) |
| Business model and economics | [Technoeconomics](topics/technoeconomics/) |
| Planning and execution | [Milestones](topics/milestones/), [How to move fast](topics/how-to-move-fast/) |
| Sales and communication | [Selling](topics/selling/), [Storytelling](topics/storytelling/) |
| Founders and teams | [Traits of great founders](topics/traits-of-great-founders/), [Building an AI-first organization](topics/building-an-ai-first-organization/) |
| Purpose and resilience | [Raison d'etre](topics/raison-detre/), [Resilience](topics/resilience-with-hillary-allen/) |

The [full topic index](topics/README.md) lists every session, including sessions without archived slides or transcripts. New class notes can be added alongside this source collection with their own attribution.

## Fifty Years source material

- [Original 50/50 Content page](https://fiftyyears.notion.site/content-c9) and [archived page text](data/content.md)
- [Recordings and transcripts](transcripts/README.md), with links to the original videos
- [Lecture slides and extracted text](data/lectures/README.md), with links to the source lecture rows and PDFs
- [Original Startup Perks page](https://fiftyyears.notion.site/5050-startup-perks-benefits) and [archived page text](data/startup-perks/content.md)

Raw public-page records are in `data/`; downloaded presentation files are in `presentations/`. The source indexes preserve the Fifty Years and C9 names so readers can trace material back to its origin.

## Refresh the Fifty Years archive

`python3 scripts/scrape.py` refreshes the public Content page, its embedded database rows, linked YouTube metadata, and presentation attachments. `python3 scripts/scrape_more.py` also refreshes the Startup Perks page and a C9 Humans directory. The Humans directory contains personal profiles and stays in ignored `data/c9-humans/`; it must not be committed. The C9 calendar is skipped.

Run `python3 scripts/fetch_transcripts.py` for available video captions and the published Loom transcript, then `python3 scripts/organize_topics.py` to rebuild the topic index. The transcript command requires `youtube_transcript_api` (`uv tool install youtube-transcript-api`).

To regenerate slide text after downloading PDFs, install `rapidocr` and `onnxruntime` in a Python environment, ensure Poppler's `pdfinfo`, `pdftotext`, and `pdftoppm` are available, then run `python3 scripts/extract_slides.py`. OCR may contain errors; the visual-only Resilience deck includes brief visual notes.

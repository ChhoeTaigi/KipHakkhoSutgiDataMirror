# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Data mirror for the Taiwan Ministry of Education's subject terminology Taigi translation data (教育部學科術語臺灣台語/臺灣客語對譯查詢, stti.moe.edu.tw). Part of the ChhoeTaigi project. The repo downloads the terminology ODS spreadsheet, converts it to CSV/JSON, and hosts everything via GitHub Pages.

Licensed under the site's 網站資料開放宣告 (open data declaration): free reuse, adaptation and redistribution with attribution. See `LICENSE.png`.

## Commands

```bash
# Activate the Python 3.12 venv
source .venv/bin/activate

# Run the full update pipeline (scrapes the download page for the current ODS link,
# downloads it, compares SHA256 against public/manifest.json, converts ODS → CSV/JSON)
python script/update_data.py

# Run only the ODS → CSV/JSON conversion
python script/convert_KipHakkhoSutgiData.py <input.ods> <output.csv> <output.json>
```

Dependencies: `requests` only. Install with `pip install requests`. The converter uses the standard library (zipfile + ElementTree).

## Architecture

### Data Pipeline (`script/`)

1. **`update_data.py`** — Main entry point. Scrapes `https://stti.moe.edu.tw/file-download/newsData/?lang=sutgi` for the `.ods` link (the filename is dated, e.g. `ttg_20241219.ods`), downloads it, compares its SHA256 hash against `public/manifest.json`, creates a timestamped version directory on change, and calls the converter.

2. **`convert_KipHakkhoSutgiData.py`** — Reads the single sheet `學科術語綜整檔` directly from the ODS XML. Cells with several `<text:p>` paragraphs are joined with `\n` (pandas' odf reader would concatenate them without a separator). Then per row: merges `第1階段`–`第5階段` into `分類` (lines `學習領域-學習階段-科目`), renames `序號` → `編號`, `學科術語` → `中文`, `參考解釋` → `中文解說`, `臺灣台語詞彙` → `臺灣台語詞彙(漢字)` and `臺羅` → `KPL`, and adds `POJ` after `KPL`. Output: one row per term in CSV and a JSON array of objects. `編號` is an integer.

3. **`kpl_to_poj.py`** — KPL (臺羅) Unicode → POJ Unicode, a Python port of the relevant parts of KonvertToPOJ (`FhlDictHuDataMirror/lib/KonvertToPOJ`): strip tone mark → swap letters (ts→ch, tsh→chh, ua→oa, ue→oe, ik→ek, ing→eng, oo→o͘, nn→ⁿ) → re-place the tone by POJ Section 21 rules. Tokens that are not valid KPL syllables (acronyms, CJK, punctuation) pass through unchanged.

### Data Layout (`public/`)

```
public/
  manifest.json              # Latest version, source URL/filename, file hash
  {YYYYMMDD-HHMM}/           # Timestamped version directory
    bunji/                    # Converted text data (CSV + JSON)
    tangloo/                  # Original download (ODS) — gitignored
```

### Hosting

- `index.md` is the GitHub Pages landing page
- `.nojekyll` disables Jekyll processing

## Important Rules

- **`README.md` and `index.md` must stay in sync.** They have identical content. When updating version references or any other content in one, always update the other to match.
- After running the update pipeline, update the version ID, date, and source filename in both `README.md` and `index.md`.

## Terminology (Taigi)

- **bunji** (文字) — text data
- **tangloo** (檔路) — file storage / archives
- **Hakkho Sutgi** (學科術語) — subject terminology
- **hun-lūi** (分類) — classification (the merged curriculum column)
- **KipHakkhoSutgiData** (教育部學科術語資料) — terminology data

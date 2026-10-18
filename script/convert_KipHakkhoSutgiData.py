"""Convert the KipHakkhoSutgi ODS (學科術語綜整檔) into CSV and JSON.

The ODS is a single flat sheet. Many cells hold several paragraphs
(e.g. multiple 臺羅 readings or multiple curriculum stages); pandas' odf
reader concatenates those without a separator, so this converter reads the
ODS XML directly and joins paragraphs with "\n", keeping the data faithful
to the source.
"""

import csv
import json
import os
import sys
import zipfile
import xml.etree.ElementTree as ET

NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}
T = "{%s}" % NS["table"]
TX = "{%s}" % NS["text"]
OF = "{%s}" % NS["office"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "public")

INPUT_FILE = os.path.join(DATA_DIR, "KipHakkhoSutgiData.ods")
CSV_OUTPUT = os.path.join(DATA_DIR, "KipHakkhoSutgiData.csv")
JSON_OUTPUT = os.path.join(DATA_DIR, "KipHakkhoSutgiData.json")

INTEGER_COLUMNS = {"序號"}

# The source spreads curriculum classification over five columns 第1階段..第5階段,
# each holding "學習領域-科目" lines. They are merged into one `分類` (hun-lūi)
# column whose lines read "學習領域-學習階段-科目".
STAGE_COLUMNS = [f"第{i}階段" for i in range(1, 6)]
HUNLUI_COLUMN = "分類"

# Source column → published column name.
RENAME_COLUMNS = {
    "序號": "編號",
    "學科術語": "中文",
    "參考解釋": "中文解說",
    "臺灣台語詞彙": "臺灣台語詞彙(漢字)",
    "臺羅": "KPL",
}

# Source columns the conversion depends on; a renamed or dropped one is an error.
REQUIRED_COLUMNS = list(RENAME_COLUMNS) + STAGE_COLUMNS

# Every term has its own page on the source site, addressed by 序號 (published as 編號):
# https://stti.moe.edu.tw/search/search-result/100071/?lang=sutgi → 三角形. The link is
# appended as the last column. SITE is shared with update_data.py.
SITE = "https://stti.moe.edu.tw"
ID_COLUMN = RENAME_COLUMNS["序號"]
URL_COLUMN = "網址"
URL_TEMPLATE = SITE + "/search/search-result/{}/?lang=sutgi"


def _paragraph_text(p):
    """Flatten a <text:p>, expanding <text:s>, <text:tab>, <text:line-break>."""
    parts = [p.text or ""]
    for child in p:
        tag = child.tag
        if tag == TX + "s":
            parts.append(" " * int(child.get(TX + "c", "1")))
        elif tag == TX + "tab":
            parts.append("\t")
        elif tag == TX + "line-break":
            parts.append("\n")
        else:
            parts.append("".join(child.itertext()))
        parts.append(child.tail or "")
    return "".join(parts)


def _cell_text(cell):
    paragraphs = [_paragraph_text(p) for p in cell.findall(TX + "p")]
    # Drop trailing empty paragraphs (the source has stray empty <text:p/>)
    while paragraphs and paragraphs[-1].strip() == "":
        paragraphs.pop()
    return "\n".join(p.strip() for p in paragraphs)


def _iter_rows(table):
    for row in table.iter(T + "table-row"):
        repeat = int(row.get(T + "number-rows-repeated", "1"))
        values = []
        for cell in row:
            if cell.tag not in (T + "table-cell", T + "covered-table-cell"):
                continue
            n = int(cell.get(T + "number-columns-repeated", "1"))
            text = _cell_text(cell)
            # A huge repeat count means trailing empty filler; cap it.
            if text == "" and n > 1000:
                n = 1
            values.extend([text] * n)
        while values and values[-1] == "":
            values.pop()
        if not values:
            continue
        for _ in range(min(repeat, 1000)):
            yield values


def read_ods(path):
    """Return (sheet_name, header, rows) for the first sheet of an ODS file."""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("content.xml"))
    table = root.find(".//" + T + "table")
    if table is None:
        raise ValueError("No table found in ODS")
    sheet_name = table.get(T + "name")
    rows = _iter_rows(table)
    header = next(rows)
    records = []
    for values in rows:
        values = values + [""] * (len(header) - len(values))
        records.append(dict(zip(header, values[: len(header)])))
    return sheet_name, header, records


def _coerce(record):
    out = {}
    for k, v in record.items():
        if k in INTEGER_COLUMNS and v.strip().lstrip("-").isdigit():
            out[k] = int(v)
        else:
            out[k] = v
    return out


def _merge_hunlui(record):
    """Replace 第1階段..第5階段 with a single `分類` (hun-lūi) column.

    "社會-生活課程" in 第1階段 becomes "社會-第1階段-生活課程". A few source lines
    carry only the 學習領域 (no 科目); those become "學習領域-第N階段".
    """
    lines = []
    for stage in STAGE_COLUMNS:
        for line in record.get(stage, "").split("\n"):
            line = line.strip()
            if not line:
                continue
            field, sep, subject = line.partition("-")
            lines.append(f"{field}-{stage}-{subject}" if sep else f"{field}-{stage}")
    out = {}
    inserted = False
    for k, v in record.items():
        if k in STAGE_COLUMNS:
            if not inserted:
                out[HUNLUI_COLUMN] = "\n".join(lines)
                inserted = True
            continue
        out[k] = v
    if not inserted:
        out[HUNLUI_COLUMN] = "\n".join(lines)
    return out


def _rename(record):
    return {RENAME_COLUMNS.get(k, k): v for k, v in record.items()}


def _add_url(record):
    """Append the term's page on the source site, built from its 編號 (empty unless numeric)."""
    term_id = record.get(ID_COLUMN)
    url = URL_TEMPLATE.format(term_id) if isinstance(term_id, int) else ""
    return {**record, URL_COLUMN: url}


def _transform(record):
    return _add_url(_rename(_merge_hunlui(_coerce(record))))


def convert_KipHakkhoSutgiData(input_file=INPUT_FILE, csv_output=CSV_OUTPUT, json_output=JSON_OUTPUT):
    print(f"Reading {input_file}...")
    sheet_name, header, records = read_ods(input_file)
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise ValueError(f"Sheet '{sheet_name}' lacks expected source column(s): {missing}")
    records = [_transform(r) for r in records]
    # Derive the published header from the source header, so even a header-only
    # sheet is written with the documented columns.
    header = list(_transform(dict.fromkeys(header, "")).keys())
    print(f"Sheet '{sheet_name}': {len(records)} rows, columns: {header}")

    os.makedirs(os.path.dirname(csv_output), exist_ok=True)
    with open(csv_output, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(records)
    print(f"Wrote {csv_output}")

    with open(json_output, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"Wrote {json_output}")
    return records


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 3:
        convert_KipHakkhoSutgiData(*args)
    else:
        convert_KipHakkhoSutgiData()

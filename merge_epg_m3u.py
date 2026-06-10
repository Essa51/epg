#!/usr/bin/env python3
# merge_epg_m3u.py
import requests, re, os, zipfile, xml.etree.ElementTree as ET
from pathlib import Path

# ----- اضبط هذه القيم إذا تحتاج -----
DROPBOX_M3U = "https://www.dropbox.com/scl/fi/2orac50oxwxqt3pqfgcpi/_1TeestPlayllistlion.txt?rlkey=lnfzaaugig09nv2uanheww0cl&st=39swgzp2&dl=1"
EPG_CDN = "https://cdn.jsdelivr.net/gh/Essa51/arabic_epg.xml@v1.0/arabic_clean_epg.xml"
OUTPUT_DIR = Path(".")
OUTPUT_M3U = OUTPUT_DIR / "final_m3u.m3u"
OUTPUT_EPG = OUTPUT_DIR / "final_epg.xml"
REPORTS_DIR = OUTPUT_DIR / "reports"
ZIP_OUTPUT = OUTPUT_DIR / "merged_epg_m3u.zip"
# ------------------------------------

REPORTS_DIR.mkdir(parents=True, exist_ok=True)

def download_text(url, timeout=60):
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content.decode("utf-8", errors="ignore")

def norm(s):
    if not s: return ""
    return re.sub(r"\s+", " ", s.strip().lower())

def parse_epg(epg_text):
    root = ET.fromstring(epg_text)
    epg_ids = set()
    name_to_id = {}
    for ch in root.findall(".//channel"):
        ch_id = ch.get("id") or ""
        if ch_id:
            epg_ids.add(ch_id)
        dn = ch.find("display-name")
        if dn is None:
            for child in ch:
                if child.tag.lower().endswith("display-name"):
                    dn = child
                    break
        if dn is not None and dn.text:
            name_to_id[norm(dn.text)] = ch_id
    return epg_ids, name_to_id

def parse_m3u(text):
    lines = text.splitlines()
    entries = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.upper().startswith("#EXTINF"):
            ext = line
            stream = lines[i+1].strip() if i+1 < len(lines) else ""
            attrs = {}
            for m in re.finditer(r'([a-zA-Z0-9\-]+)=["\']([^"\']+)["\']', ext):
                attrs[m.group(1)] = m.group(2)
            mname = re.search(r',\s*(.+)$', ext)
            name = mname.group(1).strip() if mname else ""
            entries.append({"ext": ext, "stream": stream, "attrs": attrs, "name": name})
            i += 2
        else:
            i += 1
    return entries

def rebuild_extinf(e):
    prefix_m = re.match(r'(#EXTINF:[^ ]*)(.*)', e['ext'], re.IGNORECASE)
    prefix = prefix_m.group(1) if prefix_m else "#EXTINF:-1"
    attr_parts = []
    if 'tvg-id' in e['attrs']:
        attr_parts.append(f'tvg-id="{e['attrs']['tvg-id']}"')
    for k,v in e['attrs'].items():
        if k == 'tvg-id': continue
        attr_parts.append(f'{k}="{v}"')
    attrs_str = " ".join(attr_parts).strip()
    name = e['name'] or ""
    if attrs_str:
        return f"{prefix} {attrs_str}, {name}".strip()
    else:
        return f"{prefix},{name}".strip()

def main():
    print("Downloading EPG...")
    epg_text = download_text(EPG_CDN)
    OUTPUT_EPG.write_text(epg_text, encoding="utf-8")
    epg_ids, name_to_id = parse_epg(epg_text)
    print(f"EPG channels: {len(epg_ids)}, names mapped: {len(name_to_id)}")

    print("Downloading M3U...")
    m3u_text = download_text(DROPBOX_M3U)
    entries = parse_m3u(m3u_text)
    print(f"Parsed entries: {len(entries)} (with tvg-id: {sum(1 for e in entries if 'tvg-id' in e['attrs'])})")

    kept = []
    missing = []
    for e in entries:
        tvg = e['attrs'].get('tvg-id')
        assigned = None
        if tvg and tvg in epg_ids:
            assigned = tvg
        else:
            n = norm(e['name'])
            if n and n in name_to_id and name_to_id[n]:
                assigned = name_to_id[n]
        if assigned:
            e['attrs']['tvg-id'] = assigned
            kept.append(e)
        else:
            missing.append(e)

    print(f"Kept after matching: {len(kept)}, Missing: {len(missing)}")

    with OUTPUT_M3U.open("w", encoding="utf-8") as f:
        f.write(f'#EXTM3U tvg-url="{EPG_CDN}"\n')
        for e in kept:
            f.write(rebuild_extinf(e) + "\n")
            f.write((e['stream'] or "") + "\n")

    missing_path = REPORTS_DIR / "missing_tvg_ids.txt"
    with missing_path.open("w", encoding="utf-8") as f:
        for e in missing:
            f.write((e['attrs'].get('tvg-id','')) + "\t" + e['name'] + "\t" + e['stream'] + "\n")

    with zipfile.ZipFile(ZIP_OUTPUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(OUTPUT_EPG)
        z.write(OUTPUT_M3U)

    print("Created:", OUTPUT_M3U, OUTPUT_EPG, missing_path, ZIP_OUTPUT)

if __name__ == "__main__":
    main()

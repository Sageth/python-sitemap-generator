#!/usr/bin/env python3
"""
Memory-efficient sitemap generator

- Streams HTML files to sitemap parts immediately (no full page_data in memory)
- Extracts images and videos (canonical)
- Auto-splits at 1000 URLs per part by default
- Generates sitemap_index.xml
"""

import argparse
import re
import xml.etree.ElementTree as eTree
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.dom import minidom

from bs4 import BeautifulSoup
from tqdm import tqdm

VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".wmv"}
HTML_EXTENSIONS = {".htm", ".html"}
XML_STYLESHEET = '<?xml-stylesheet type="text/xsl" href="/sitemap-style.xsl" ?>\n'


def write_url_element(f, page_url, lastmod_date, image_urls, video_data, image_seen, video_seen):
    f.write("  <url>\n")
    f.write(f"    <loc>{page_url}</loc>\n")
    f.write(f"    <lastmod>{lastmod_date}</lastmod>\n")
    f.write("    <changefreq>weekly</changefreq>\n")
    f.write("    <priority>0.5</priority>\n")

    for img_url in sorted(image_urls):
        if img_url in image_seen:
            continue
        f.write("    <image:image>\n")
        f.write(f"      <image:loc>{img_url}</image:loc>\n")
        f.write("    </image:image>\n")
        image_seen.add(img_url)

    for video_url, title, desc in video_data:
        if video_url in video_seen:
            continue
        f.write("    <video:video>\n")
        f.write(f"      <video:content_loc>{video_url}</video:content_loc>\n")
        f.write(f"      <video:title>{title}</video:title>\n")
        f.write(f"      <video:description>{desc}</video:description>\n")
        f.write("    </video:video>\n")
        video_seen.add(video_url)

    f.write("  </url>\n")


def generate_sitemap_parts_streamed(html_files, site_base_url, output_dir, site_root, split_limit=1000):
    output_dir = Path(output_dir).resolve()
    site_root = Path(site_root).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    part_files = []
    image_seen = set()
    video_seen = set()
    part_file = None
    urls_in_part = 0
    part_count = 0

    for file_path in tqdm(html_files, desc="Processing HTML files"):
        if part_file is None or urls_in_part >= split_limit:
            if part_file:
                part_file.write("</urlset>\n")
                part_file.close()
            part_count += 1
            part_file_path = output_dir / f"sitemap-{part_count}.xml"
            part_file = open(part_file_path, "w", encoding="utf-8")
            part_file.write('<?xml version="1.0" encoding="utf-8"?>\n')
            part_file.write(XML_STYLESHEET)
            part_file.write('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n')
            part_file.write('        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"\n')
            part_file.write('        xmlns:video="http://www.google.com/schemas/sitemap-video/1.1">\n')
            urls_in_part = 0
            part_files.append(part_file_path)

        # Make relative path from site_root, not first HTML file
        rel_path = file_path.relative_to(site_root)
        page_url = urljoin(site_base_url.rstrip("/") + "/", rel_path.as_posix())
        mtime = file_path.stat().st_mtime
        lastmod_date = datetime.fromtimestamp(mtime, tz=timezone.utc).replace(microsecond=0).astimezone().isoformat()

        html = file_path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "lxml")
        image_urls = {urljoin(page_url, img.get("src")) for img in soup.find_all("img") if img.get("src")}

        video_data = []
        for video_tag in soup.find_all("video"):
            video_src = video_tag.get("src") or (video_tag.find("source") and video_tag.find("source").get("src"))
            if not video_src or Path(video_src).suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            video_url = urljoin(page_url, video_src)
            title = video_tag.get("title") or video_tag.get("data-title") or "Untitled"
            desc = video_tag.get("description") or video_tag.get("data-description") or title
            video_data.append((video_url, title, desc))

        write_url_element(part_file, page_url, lastmod_date, image_urls, video_data, image_seen, video_seen)
        urls_in_part += 1

    if part_file:
        part_file.write("</urlset>\n")
        part_file.close()

    return part_files, image_seen, video_seen


def cleanup_old_parts(output_dir: Path, part_prefix, part_files_current):
    current_filenames = set(Path(f).name for f in part_files_current)
    existing_files = list(output_dir.glob(f"{part_prefix}-*.xml"))
    pattern = re.compile(rf"^{re.escape(part_prefix)}-\d+\.xml$")
    removed_count = 0
    for file_path in existing_files:
        if pattern.match(file_path.name) and file_path.name not in current_filenames:
            try:
                file_path.unlink()
                removed_count += 1
                print(f"🗑️ Deleted old part file: {file_path}")
            except Exception as e:
                print(f"⚠️ Error deleting {file_path}: {e}")
    if removed_count == 0:
        print("✅ No old part files found.")
    else:
        print(f"✅ Removed {removed_count} old part file(s).")


def generate_sitemap_index(part_files, output_dir: Path, site_base_url):
    parsed_base_url = urlparse(site_base_url)
    sitemap_base_url = f"{parsed_base_url.scheme}://{parsed_base_url.netloc}/"
    index_filename = output_dir / "sitemap_index.xml"

    sitemapindex = eTree.Element("sitemapindex", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"})
    now = datetime.now(timezone.utc).replace(microsecond=0).astimezone().isoformat()

    for part_path in part_files:
        sitemap_elem = eTree.SubElement(sitemapindex, "sitemap")
        eTree.SubElement(sitemap_elem, "loc").text = urljoin(sitemap_base_url, part_path.name)
        eTree.SubElement(sitemap_elem, "lastmod").text = now

    # Serialize and pretty-print
    rough_string = eTree.tostring(sitemapindex, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ")

    with index_filename.open("w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n')
        f.write(XML_STYLESHEET)
        # Strip the duplicate declaration from minidom output
        f.write("\n".join(pretty_xml.splitlines()[1:]))

    return index_filename, urljoin(sitemap_base_url, index_filename.name)


def copy_stylesheet_to_site(site_root: Path, stylesheet_src: Path):
    destination = site_root / "sitemap-style.xsl"
    try:
        destination.write_text(stylesheet_src.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"✅ Copied sitemap stylesheet to: {destination}")
    except Exception as e:
        print(f"⚠️ Failed to copy stylesheet: {e}")


def main():
    parser = argparse.ArgumentParser(description="Memory-efficient sitemap generator")
    parser.add_argument("--site_base_url", required=True, help="Base URL of the site")
    parser.add_argument("--site_root", required=True, help="Path to site's HTML files")
    parser.add_argument("--output", default="sitemap_index.xml", help="Output sitemap index filename")
    parser.add_argument("--split", type=int, default=1000, help="Max URLs per sitemap part")
    args = parser.parse_args()

    site_root_path = Path(args.site_root).resolve()
    output_path = Path(args.output)
    if output_path.parent == Path("."):
        output_path = site_root_path / output_path.name

    # Gather all HTML files
    html_files = [f for f in site_root_path.rglob("*") if f.suffix.lower() in HTML_EXTENSIONS]
    print(f"Scanning {len(html_files)} HTML files...")

    # Generate sitemap parts (streamed)
    part_files, image_seen, video_seen = generate_sitemap_parts_streamed(
        html_files,
        args.site_base_url,
        output_path.parent,
        site_root_path,
        split_limit=args.split
    )

    # Cleanup old parts
    part_prefix = "sitemap"
    cleanup_old_parts(output_path.parent, part_prefix, part_files)

    # Generate sitemap index
    index_file, sitemap_index_url = generate_sitemap_index(part_files, output_path.parent, args.site_base_url)

    # Copy stylesheet
    script_dir = Path(__file__).parent.resolve()
    copy_stylesheet_to_site(site_root_path, script_dir / "templates/sitemap-style.xsl")

    # Summary
    print(f"\n📄 Sitemap index: {index_file}")
    print(f"  Sitemap parts: {len(part_files)}")
    print(f"  Unique images: {len(image_seen)}")
    print(f"  Unique videos: {len(video_seen)}")
    print(f"\n🔗 Submit this URL to search engines: {sitemap_index_url}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
sitemap.py

- Recursively scan .htm/.html files, extract images and videos, and generate sitemap.xml split as needed.
- Each page will be included (even if no images or videos).
- Images and videos (if present) are nested under the page.
- <lastmod> is based on the HTML file's filesystem modification date.
- Includes changefreq and priority.
- Each media will appear only under the first page where it is found (canonical).
- Auto-splits at 1,000 URLs per sitemap part by default.
- Generates sitemap_index.xml, as well as sub-index files for each part.
- Reports number of URLs, unique images, and unique videos per sitemap part and total.
- Reminder to submit sitemap_index.xml to Google, Bing, and Yandex.

Usage:
python sitemap.py --site_base_url=https://example.com --site_root=/path/to/files --output=/path/to/sitemap.xml
"""

import argparse
import datetime
import math
import re
import xml.etree.ElementTree as eTree
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

xml_stylesheet = '<?xml-stylesheet type="text/xsl" href="/sitemap-style.xsl" ?>\n'
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov"}
HTML_EXTENSIONS = {".htm", ".html"}

def indent_xml(elem, level=0, space="  "):
    indent = "\n" + (level * space)
    child_indent = "\n" + ((level + 1) * space)
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = child_indent
        for child in elem:
            indent_xml(child, level + 1, space)
            if not child.tail or not child.tail.strip():
                child.tail = child_indent
        if not elem[-1].tail or not elem[-1].tail.strip():
            elem[-1].tail = indent
    else:
        if not elem.text or not elem.text.strip():
            elem.text = ''
    if level and (not elem.tail or not elem.tail.strip()):
        elem.tail = indent

def scan_html_files(site_root, site_base_url):
    page_data = {}
    html_file_count = 0
    site_root_path = Path(site_root).resolve()
    print(f"Scanning: {site_root_path}")
    for file_path in site_root_path.rglob('*'):
        if file_path.suffix.lower() not in HTML_EXTENSIONS:
            continue
        html_file_count += 1
        rel_path = file_path.relative_to(site_root_path)
        page_url = urljoin(site_base_url, rel_path.as_posix())
        mtime = file_path.stat().st_mtime
        lastmod_date = datetime.fromtimestamp(mtime, tz=timezone.utc).astimezone().isoformat()
        with file_path.open("r", encoding="utf-8", errors="ignore") as f:
            html = f.read()
        soup = BeautifulSoup(html, "html.parser")
        img_tags = soup.find_all("img")
        video_tags = soup.find_all("video")
        image_urls = set()
        video_data = []
        for img_tag in img_tags:
            img_src = img_tag.get("src")
            if img_src:
                img_url = urljoin(page_url, img_src)
                image_urls.add(img_url)
        for video_tag in video_tags:
            video_src = video_tag.get("src")
            if not video_src:
                source = video_tag.find("source")
                if source:
                    video_src = source.get("src")
            if not video_src:
                continue
            ext = Path(video_src).suffix.lower()
            if ext not in VIDEO_EXTENSIONS:
                continue
            video_url = urljoin(page_url, video_src)
            title = video_tag.get("title") or video_tag.get("data-title") or "Untitled"
            desc = video_tag.get("description") or video_tag.get("data-description") or title
            video_data.append((video_url, title, desc))
        page_data[page_url] = (lastmod_date, image_urls, video_data)
    return html_file_count, page_data

def generate_sitemap_parts(page_data, output_path: Path, site_base_url, split_limit):
    urls = list(page_data.items())
    num_urls = len(urls)
    num_parts = math.ceil(num_urls / split_limit) if split_limit > 0 else 1
    parsed_base_url = urlparse(site_base_url)
    sitemap_base_url = f"{parsed_base_url.scheme}://{parsed_base_url.netloc}/"
    output_dir = output_path.parent
    output_prefix = output_path.stem
    part_prefix = "sitemap" if output_prefix == "sitemap_index" else output_prefix
    image_seen = set()
    video_seen = set()
    part_files = []
    for part_num in range(num_parts):
        part_start = part_num * split_limit
        part_end = min(part_start + split_limit, num_urls)
        part_urls = urls[part_start:part_end]
        part_filename = output_dir / f"{part_prefix}-{part_num + 1}.xml"
        part_url = f"{sitemap_base_url}{part_filename.name}"
        part_files.append(part_url)
        urlset = eTree.Element("urlset", {
            "xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9",
            "xmlns:image": "http://www.google.com/schemas/sitemap-image/1.1",
            "xmlns:video": "http://www.google.com/schemas/sitemap-video/1.1"
        })
        part_image_seen = set()
        part_video_seen = set()
        for page_url, (lastmod_date, image_urls, video_data) in part_urls:
            url_elem = eTree.SubElement(urlset, "url")
            eTree.SubElement(url_elem, "loc").text = page_url
            eTree.SubElement(url_elem, "lastmod").text = lastmod_date
            eTree.SubElement(url_elem, "changefreq").text = "weekly"
            eTree.SubElement(url_elem, "priority").text = "0.5"
            for img_url in sorted(image_urls):
                if img_url in image_seen:
                    continue
                image_elem = eTree.SubElement(url_elem, "image:image")
                eTree.SubElement(image_elem, "image:loc").text = img_url
                image_seen.add(img_url)
                part_image_seen.add(img_url)
            for video_url, title, desc in video_data:
                if video_url in video_seen:
                    continue
                video_elem = eTree.SubElement(url_elem, "video:video")
                eTree.SubElement(video_elem, "video:content_loc").text = video_url
                eTree.SubElement(video_elem, "video:title").text = title
                eTree.SubElement(video_elem, "video:description").text = desc
                video_seen.add(video_url)
                part_video_seen.add(video_url)
        tree = eTree.ElementTree(urlset)
        indent_xml(tree.getroot(), space="  ")
        with part_filename.open("w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n')
            f.write(xml_stylesheet)
            tree.write(f, encoding="unicode")
        print(f"Written part {part_num + 1}: {part_filename} ({part_end - part_start} URLs, {len(part_image_seen)} images, {len(part_video_seen)} videos)")
    return part_files, image_seen, video_seen

def cleanup_old_parts(output_dir: Path, part_prefix, part_files_current):
    print("\nChecking for old sitemap part files to clean up...")
    current_filenames = set(Path(url).name for url in part_files_current)
    existing_files = list(output_dir.glob(f"{part_prefix}-*.xml"))
    part_file_pattern = re.compile(rf"^{re.escape(part_prefix)}-\d+\.xml$")
    removed_count = 0
    for file_path in existing_files:
        if not part_file_pattern.match(file_path.name):
            continue
        if file_path.name not in current_filenames:
            try:
                file_path.unlink()
                print(f"🗑️ Deleted old part file: {file_path}")
                removed_count += 1
            except Exception as e:
                print(f"⚠️ Error deleting {file_path}: {e}")
    if removed_count == 0:
        print("✅ No old part files found.")
    else:
        print(f"✅ Removed {removed_count} old part file(s).")

def copy_stylesheet_to_site(site_root: Path, stylesheet_src: Path):
    destination = site_root / "sitemap-style.xsl"
    try:
        destination.write_text(stylesheet_src.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"✅ Copied sitemap stylesheet to: {destination}")
    except Exception as e:
        print(f"⚠️ Failed to copy sitemap stylesheet: {e}")

def generate_sitemap_index(part_files, output_dir: Path, site_base_url):
    parsed_base_url = urlparse(site_base_url)
    sitemap_base_url = f"{parsed_base_url.scheme}://{parsed_base_url.netloc}/"
    index_filename = output_dir / "sitemap_index.xml"

    sitemapindex = eTree.Element("sitemapindex", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"})
    now = datetime.now(timezone.utc).astimezone().isoformat()

    for part_url in part_files:
        sitemap_elem = eTree.SubElement(sitemapindex, "sitemap")
        eTree.SubElement(sitemap_elem, "loc").text = part_url
        eTree.SubElement(sitemap_elem, "lastmod").text = now

    tree = eTree.ElementTree(sitemapindex)
    indent_xml(tree.getroot(), space="  ")

    with index_filename.open("w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n')
        f.write(xml_stylesheet)
        tree.write(f, encoding="unicode")

    print(f"\n📄 Sitemap index written: {index_filename}")
    sitemap_index_url = f"{sitemap_base_url}{index_filename.name}"
    return index_filename, sitemap_index_url

def print_summary(html_file_count, page_data, image_seen, video_seen):
    print("\n📊 Sitemap Summary:")
    print(f"  HTML files scanned : {html_file_count}")
    print(f"  Pages in sitemap   : {len(page_data)}")
    print(f"  Unique images used : {len(image_seen)}")
    print(f"  Unique videos used : {len(video_seen)}")
    print("\n✅ Done.")

def main():
    parser = argparse.ArgumentParser(description="Generate sitemap.xml from static HTML site, with auto splitting.")
    parser.add_argument("--site_base_url", required=True, help="Base URL of the site (e.g. https://example.com/)")
    parser.add_argument("--site_root", required=True, help="Local path to the site's HTML files")
    parser.add_argument("--output", default="sitemap_index.xml", help="Base output filename (default: sitemap_index.xml)")
    parser.add_argument("--split", type=int, default=1000, help="Max URLs per sitemap part (default: 1000)")
    args = parser.parse_args()
    site_root_path = Path(args.site_root).resolve()
    output_path = Path(args.output)
    if output_path.name == "sitemap_index.xml" and output_path.parent == Path("."):
        output_path = site_root_path / output_path.name
    html_file_count, page_data = scan_html_files(site_root_path, args.site_base_url)
    part_files, image_seen, video_seen = generate_sitemap_parts(page_data, output_path, args.site_base_url, args.split)
    output_dir = output_path.parent
    part_prefix = output_path.stem if output_path.stem != "sitemap_index" else "sitemap"
    cleanup_old_parts(output_dir, part_prefix, part_files)
    _, sitemap_index_url = generate_sitemap_index(part_files, output_dir, args.site_base_url)

    # Copy stylesheet to site root
    script_dir = Path(__file__).parent.resolve()
    stylesheet_src = script_dir / "templates/sitemap-style.xsl"
    copy_stylesheet_to_site(site_root_path, stylesheet_src)

    print_summary(html_file_count, page_data, image_seen, video_seen)
    print(f"\n🔗 Submit this URL to Google/Bing/Yandex: {sitemap_index_url}")

if __name__ == "__main__":
    main()
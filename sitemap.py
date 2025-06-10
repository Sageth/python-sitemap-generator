#!/usr/bin/env python3
"""
sitemap.py

- Recursively scan .htm/.html files, extract images, and generate sitemap.xml split as needed.
- Each page will be included (even if no images).
- Images (if present) are nested under the page.
- <lastmod> is based on the HTML file's filesystem modification date.
- Includes changefreq and priority.
- Each image will appear only under the first page where it is found (canonical).
- Auto-splits at 25,000 URLs per sitemap part by default.
- Generates sitemap_index.xml, as well as sub-index files for each part.
- Reports number of URLs and unique images per sitemap part and total.
- Per-part and global stats
- Reminder to submit sitemap_index.xml to Google, Bing, and Yandex.

Usage:
python sitemap.py --site_base_url=https://example.com --site_root=/path/to/files --output=/path/to/sitemap.xml
"""

import argparse
import datetime
import math
import re
import xml.etree.ElementTree as eTree
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


# ------------------------------------------------------------------------------
# Helper: Pretty print XML (works on Python 3.9+)
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

# ------------------------------------------------------------------------------
def cleanup_old_parts(output_dir: Path, part_prefix, part_files_current):
    print()
    print("Checking for old sitemap part files to clean up...")

    current_filenames = set(Path(part_url).name for part_url in part_files_current)

    # More precise: only match sitemap-NUMBER.xml
    existing_files = list(Path(output_dir).glob(f"{part_prefix}-*.xml"))

    # Only keep files that match {prefix}-{number}.xml exactly
    part_file_pattern = re.compile(rf"^{re.escape(part_prefix)}-\d+\.xml$")

    removed_count = 0

    for file_path in existing_files:
        if not part_file_pattern.match(file_path.name):
            # Skip files like sitemap-style.xml
            continue

        if file_path.name not in current_filenames:
            try:
                file_path.unlink()
                print(f"Deleted old part file: {file_path}")
                removed_count += 1
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")

    if removed_count == 0:
        print("No old part files found.")
    else:
        print(f"Removed {removed_count} old part file(s).")


# ------------------------------------------------------------------------------
def scan_html_files(site_root, site_base_url):
    page_data = {}  # page_url -> (lastmod_date, set of images)
    html_file_count = 0

    site_root_path = Path(site_root).resolve()
    print(f"Scanning: {site_root_path}")

    # Extensions to match
    extensions = {'.htm', '.html'}

    # Loop over all matching files
    for file_path in site_root_path.rglob('*'):
        if file_path.suffix.lower() not in extensions:
            continue

        html_file_count += 1
        rel_path = file_path.relative_to(site_root_path)
        page_url = urljoin(site_base_url, rel_path.as_posix())

        # Get last modified date (filesystem mtime)
        mtime = file_path.stat().st_mtime
        lastmod_date = datetime.datetime.fromtimestamp(mtime, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")

        with file_path.open("r", encoding="utf-8", errors="ignore") as f:
            html = f.read()

        soup = BeautifulSoup(html, "html.parser")
        img_tags = soup.find_all("img")

        image_urls = set()
        for img_tag in img_tags:
            img_src = img_tag.get("src")
            if not img_src:
                continue
            img_url = urljoin(page_url, img_src)
            image_urls.add(img_url)

        page_data[page_url] = (lastmod_date, image_urls)

    return html_file_count, page_data


# ------------------------------------------------------------------------------
def generate_sitemap_parts(page_data, output_path: Path, site_base_url, split_limit):
    urls = list(page_data.items())
    num_urls = len(urls)
    num_parts = math.ceil(num_urls / split_limit) if split_limit > 0 else 1

    print(f"DEBUG: num_urls = {num_urls}, split_limit = {split_limit}, num_parts = {num_parts}")
    print(f"Total pages        : {num_urls}")
    print(f"Sitemap parts      : {num_parts} (split limit {split_limit})")
    print()

    parsed_base_url = urlparse(site_base_url)
    sitemap_base_url = f"{parsed_base_url.scheme}://{parsed_base_url.netloc}/"

    output_dir = output_path.parent
    output_prefix = output_path.stem

    # If default output (sitemap_index.xml), use 'sitemap' as prefix for part files
    if output_prefix == "sitemap_index":
        part_prefix = "sitemap"
    else:
        part_prefix = output_prefix

    image_seen = set()
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
            "xmlns:image": "http://www.google.com/schemas/sitemap-image/1.1"
        })

        xml_stylesheet = '<?xml-stylesheet type="text/xsl" href="/sitemap-style.xml" ?>\n'

        part_image_seen = set()

        for page_url, (lastmod_date, image_urls) in part_urls:
            url_elem = eTree.SubElement(urlset, "url")

            loc_elem = eTree.SubElement(url_elem, "loc")
            loc_elem.text = page_url

            lastmod_elem = eTree.SubElement(url_elem, "lastmod")
            lastmod_elem.text = lastmod_date

            changefreq_elem = eTree.SubElement(url_elem, "changefreq")
            changefreq_elem.text = "weekly"

            priority_elem = eTree.SubElement(url_elem, "priority")
            priority_elem.text = "0.5"

            for img_url in sorted(image_urls):
                if img_url in image_seen:
                    continue
                image_elem = eTree.SubElement(url_elem, "image:image")
                image_loc_elem = eTree.SubElement(image_elem, "image:loc")
                image_loc_elem.text = img_url
                image_seen.add(img_url)
                part_image_seen.add(img_url)

        tree = eTree.ElementTree(urlset)
        indent_xml(tree.getroot(), space="  ")

        with part_filename.open("w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n')
            f.write(xml_stylesheet)
            tree.write(f, encoding="unicode")

        print(
            f"Written part {part_num + 1}: {part_filename} ({part_end - part_start} URLs, {len(part_image_seen)} unique images)")

    return part_files, image_seen



# ------------------------------------------------------------------------------
def generate_sitemap_index(part_files, output_dir: Path, site_base_url):
    parsed_base_url = urlparse(site_base_url)
    sitemap_base_url = f"{parsed_base_url.scheme}://{parsed_base_url.netloc}/"

    output_dir_path = Path(output_dir).resolve()
    index_filename = output_dir_path / "sitemap_index.xml"

    sitemapindex = eTree.Element("sitemapindex", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"})

    for part_url in part_files:
        sitemap_elem = eTree.SubElement(sitemapindex, "sitemap")
        loc_elem = eTree.SubElement(sitemap_elem, "loc")
        loc_elem.text = part_url

        now = datetime.datetime.now(datetime.UTC)
        lastmod_elem = eTree.SubElement(sitemap_elem, "lastmod")
        lastmod_elem.text = now.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    tree = eTree.ElementTree(sitemapindex)
    indent_xml(tree.getroot(), space="  ")

    with index_filename.open("w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n')
        tree.write(f, encoding="unicode")

    print()
    print(f"Sitemap index written: {index_filename}")

    sitemap_index_url = f"{sitemap_base_url}{index_filename.name}"
    return index_filename, sitemap_index_url


# ------------------------------------------------------------------------------
def submit_sitemap(sitemap_index_url):
    print()
    print("IMPORTANT:")
    print(f"Submit {sitemap_index_url} to Google, Bing, and Yandex as primary sitemap!")


# ------------------------------------------------------------------------------
def print_summary(html_file_count, page_data, image_seen):
    print()
    print("Done.")
    print(f"HTML files scanned : {html_file_count}")
    print(f"Pages in sitemap   : {len(page_data)}")
    print(f"Unique images used : {len(image_seen)}")


# ------------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Generate sitemap.xml from static HTML site, with auto splitting.")
    parser.add_argument("--site_base_url", required=True, help="Base URL of the site (e.g. https://example.com/)")
    parser.add_argument("--site_root", required=True, help="Local path to the site's HTML files")
    parser.add_argument("--output", default="sitemap_index.xml",
                        help="Base output filename for sitemap index (default: sitemap_index.xml)")
    parser.add_argument("--split", type=int, default=1000, help="Max URLs per sitemap part (default: 1000)")

    args = parser.parse_args()

    # Convert paths to pathlib.Path
    site_root_path = Path(args.site_root).resolve()
    output_path = Path(args.output)

    # If output path is just a filename (default), write to site_root
    if output_path.name == "sitemap_index.xml" and output_path.parent == Path("."):
        output_path = site_root_path / output_path.name

    html_file_count, page_data = scan_html_files(site_root_path, args.site_base_url)
    part_files, image_seen = generate_sitemap_parts(page_data, output_path, args.site_base_url, args.split)

    output_dir = output_path.parent

    # Determine part prefix (same logic as generate_sitemap_parts)
    output_prefix = output_path.stem
    if output_prefix == "sitemap_index":
        part_prefix = "sitemap"
    else:
        part_prefix = output_prefix

    # Cleanup old part files
    cleanup_old_parts(output_dir, part_prefix, part_files)

    # Generate sitemap index
    index_filename, sitemap_index_url = generate_sitemap_index(part_files, output_dir, args.site_base_url)

    submit_sitemap(sitemap_index_url)
    print_summary(html_file_count, page_data, image_seen)


# ------------------------------------------------------------------------------
if __name__ == "__main__":
    main()

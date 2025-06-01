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
import os
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


# ------------------------------------------------------------------------------
# Helper: Pretty print XML (works on Python 3.9+)
def indent_xml(elem, level=0, space="  "):
    i = "\n" + level * space
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + space
        for child in elem:
            indent_xml(child, level + 1, space)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


# ------------------------------------------------------------------------------
def scan_html_files(site_root, site_base_url):
    page_data = {}  # page_url -> (lastmod_date, set of images)
    html_file_count = 0

    print(f"Scanning: {site_root}")

    for root, dirs, files in os.walk(site_root):
        for filename in files:
            if filename.lower().endswith(('.htm', '.html')):
                html_file_count += 1
                file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(file_path, site_root)
                page_url = urljoin(site_base_url, rel_path.replace(os.path.sep, '/'))

                # Get last modified date (filesystem mtime)
                mtime = os.path.getmtime(file_path)
                lastmod_date = datetime.datetime.fromtimestamp(mtime, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")

                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
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
def generate_sitemap_parts(page_data, output_file, site_base_url, split_limit):
    urls = list(page_data.items())
    num_urls = len(urls)
    num_parts = math.ceil(num_urls / split_limit) if split_limit > 0 else 1

    print(f"DEBUG: num_urls = {num_urls}, split_limit = {split_limit}, num_parts = {num_parts}")

    print(f"Total pages        : {num_urls}")
    print(f"Sitemap parts      : {num_parts} (split limit {split_limit})")
    print()

    parsed_base_url = urlparse(site_base_url)
    sitemap_base_url = f"{parsed_base_url.scheme}://{parsed_base_url.netloc}/"
    output_prefix = os.path.splitext(os.path.basename(output_file))[0]
    # If default output (sitemap_index.xml), use 'sitemap' as prefix for part files
    if output_prefix == "sitemap_index":
        part_prefix = "sitemap"
    else:
        part_prefix = output_prefix

    output_dir = os.path.dirname(output_file)

    image_seen = set()
    part_files = []

    for part_num in range(num_parts):
        part_start = part_num * split_limit
        part_end = min(part_start + split_limit, num_urls)
        part_urls = urls[part_start:part_end]

        part_filename = os.path.join(output_dir, f"{part_prefix}-{part_num + 1}.xml")
        part_url = f"{sitemap_base_url}{os.path.basename(part_filename)}"

        part_files.append(part_url)

        urlset = ET.Element("urlset", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9",
                                       "xmlns:image": "http://www.google.com/schemas/sitemap-image/1.1"})

        xml_stylesheet = '<?xml-stylesheet type="text/xsl" href="/sitemap-style.xml" ?>\n'

        part_image_seen = set()

        for page_url, (lastmod_date, image_urls) in part_urls:
            url_elem = ET.SubElement(urlset, "url")

            loc_elem = ET.SubElement(url_elem, "loc")
            loc_elem.text = page_url

            lastmod_elem = ET.SubElement(url_elem, "lastmod")
            lastmod_elem.text = lastmod_date

            changefreq_elem = ET.SubElement(url_elem, "changefreq")
            changefreq_elem.text = "weekly"

            priority_elem = ET.SubElement(url_elem, "priority")
            priority_elem.text = "0.5"

            for img_url in sorted(image_urls):
                if img_url in image_seen:
                    continue
                image_elem = ET.SubElement(url_elem, "image:image")
                image_loc_elem = ET.SubElement(image_elem, "image:loc")
                image_loc_elem.text = img_url
                image_seen.add(img_url)
                part_image_seen.add(img_url)

        tree = ET.ElementTree(urlset)
        indent_xml(tree.getroot(), space="  ")

        with open(part_filename, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n')
            f.write(xml_stylesheet)
            tree.write(f, encoding="unicode")

        print(
            f"Written part {part_num + 1}: {part_filename} ({part_end - part_start} URLs, {len(part_image_seen)} unique images)")

    return part_files, image_seen


# ------------------------------------------------------------------------------
def generate_sitemap_index(part_files, output_dir, site_base_url):
    parsed_base_url = urlparse(site_base_url)
    sitemap_base_url = f"{parsed_base_url.scheme}://{parsed_base_url.netloc}/"

    index_filename = os.path.join(output_dir, "sitemap_index.xml")
    sitemapindex = ET.Element("sitemapindex", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"})

    for part_url in part_files:
        sitemap_elem = ET.SubElement(sitemapindex, "sitemap")
        loc_elem = ET.SubElement(sitemap_elem, "loc")
        loc_elem.text = part_url

        now = datetime.datetime.now(datetime.UTC)
        lastmod_elem = ET.SubElement(sitemap_elem, "lastmod")
        lastmod_elem.text = now.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    tree = ET.ElementTree(sitemapindex)
    indent_xml(tree.getroot(), space="  ")
    with open(index_filename, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n')
        tree.write(f, encoding="unicode")

    print()
    print(f"Sitemap index written: {index_filename}")

    sitemap_index_url = f"{sitemap_base_url}{os.path.basename(index_filename)}"
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
    parser.add_argument("--split", type=int, default=25000, help="Max URLs per sitemap part (default: 25000)")

    args = parser.parse_args()

    # If output path is just a filename (default), write to site_root
    if args.output == "sitemap_index.xml" or os.path.basename(args.output) == args.output:
        args.output = os.path.join(args.site_root, args.output)

    html_file_count, page_data = scan_html_files(args.site_root, args.site_base_url)
    part_files, image_seen = generate_sitemap_parts(page_data, args.output, args.site_base_url, args.split)

    # Always generate sitemap index (even if 1 part — makes auto-submit easier)
    output_dir = os.path.dirname(args.output)
    index_filename, sitemap_index_url = generate_sitemap_index(part_files, output_dir, args.site_base_url)

    submit_sitemap(sitemap_index_url)
    print_summary(html_file_count, page_data, image_seen)


# ------------------------------------------------------------------------------
if __name__ == "__main__":
    main()

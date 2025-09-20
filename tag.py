import os
import shutil
from copy import deepcopy
from bs4 import BeautifulSoup

root_dir = "/media/sage/crucial1/dvrbs/dvrbs.camdenhistory.com"
tag_html = '<link rel="preconnect" href="https://assets.dvrbs.camdenhistory.com" crossorigin>'
extensions = {".html", ".htm"}

# Parse the tag once, outside the loop
new_tag_template = BeautifulSoup(tag_html, "html.parser").link

# Counters
added_count = 0
updated_count = 0
skipped_count = 0
nohead_count = 0
error_count = 0

for dirpath, _, filenames in os.walk(root_dir):
    for filename in filenames:
        if os.path.splitext(filename)[1].lower() in extensions:
            filepath = os.path.join(dirpath, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    soup = BeautifulSoup(f, "html.parser")
            except Exception as e:
                print(f"⚠️ Skipping {filepath}: {e}")
                error_count += 1
                continue

            # Match any link with the correct href and a rel containing "preconnect"
            existing = soup.find(
                "link",
                href="https://assets.dvrbs.camdenhistory.com",
                rel=lambda r: r and (
                    ("preconnect" in r) if isinstance(r, list)
                    else "preconnect" in r.lower()
                )
            )

            if existing:
                # Upgrade it if crossorigin is missing
                if not existing.has_attr("crossorigin"):
                    existing["crossorigin"] = "crossorigin"

                    # Backup before writing
                    backup_path = filepath + ".bak"
                    if not os.path.exists(backup_path):
                        os.rename(filepath, backup_path)
                    else:
                        shutil.copy2(filepath, backup_path)

                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(soup.decode())

                    print(f"🔧 Updated tag in {filepath}")
                    updated_count += 1
                else:
                    print(f"⏭️  Skipped (already correct): {filepath}")
                    skipped_count += 1
                continue

            head_tag = soup.head or soup.find("head")
            if head_tag:
                # Clone the pre-parsed tag
                new_tag = deepcopy(new_tag_template)

                # Only insert newline if the first element isn't already whitespace
                if not (head_tag.contents and isinstance(head_tag.contents[0], str) and head_tag.contents[0].strip() == ""):
                    head_tag.insert(0, soup.new_string("\n    "))
                    head_tag.insert(1, new_tag)
                else:
                    head_tag.insert(1, new_tag)

                # Backup before writing
                backup_path = filepath + ".bak"
                if not os.path.exists(backup_path):
                    os.rename(filepath, backup_path)
                else:
                    shutil.copy2(filepath, backup_path)

                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(soup.decode())

                print(f"✅ Added tag to {filepath}")
                added_count += 1
            else:
                print(f"⚠️ No <head> found in {filepath}")
                nohead_count += 1

# Summary
print("\n--- Summary ---")
print(f"✅ Added:   {added_count}")
print(f"🔧 Updated: {updated_count}")
print(f"⏭️  Skipped: {skipped_count}")
print(f"⚠️  No <head>: {nohead_count}")
print(f"❌ Errors:  {error_count}")

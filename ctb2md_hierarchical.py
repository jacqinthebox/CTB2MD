#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CTB2MD Hierarchical - Exports CherryTree to Obsidian with folder structure
Skips empty top-level nodes, preserves hierarchy
Supports password-protected .ctb files
"""

import os
import sqlite3
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import re
import tempfile
import shutil
import xml.etree.ElementTree as ET
import json
import base64

# Optional: for password-protected files
try:
    import py7zr
    HAS_PY7ZR = True
except ImportError:
    HAS_PY7ZR = False

# Settings file location
# When running as compiled app, use Application Support folder
# When running as script, use same directory as script
import sys
if getattr(sys, 'frozen', False):
    # Running as compiled app - use Application Support
    APP_SUPPORT = os.path.expanduser("~/Library/Application Support/CTB2MD")
    os.makedirs(APP_SUPPORT, exist_ok=True)
    SETTINGS_FILE = os.path.join(APP_SUPPORT, "settings.json")
else:
    # Running as script - use script directory
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    SETTINGS_FILE = os.path.join(SCRIPT_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "input_dir": os.path.expanduser("~"),
    "output_dir": os.path.expanduser("~")
}


def load_settings():
    """Load settings from file or return defaults"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                # Merge with defaults in case new settings were added
                return {**DEFAULT_SETTINGS, **settings}
    except Exception:
        pass
    return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    """Save settings to file"""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save settings: {e}")


class CTB2MD:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()

        # Load settings
        self.settings = load_settings()

        file_path = filedialog.askopenfilename(
            title="Choose a CherryTree file",
            initialdir=self.settings.get("input_dir", os.path.expanduser("~")),
            filetypes=[
                ("CherryTree files", "*.ctb *.ctz *.ctd *.ctx"),
                ("SQLite format", "*.ctb *.ctz"),
                ("XML format", "*.ctd *.ctx"),
                ("All files", "*.*")
            ]
        )

        if file_path:
            # Save input directory for next time
            self.settings["input_dir"] = os.path.dirname(file_path)

            # Ask for output folder
            output_dir = filedialog.askdirectory(
                title="Choose output folder for Markdown files",
                initialdir=self.settings.get("output_dir", os.path.dirname(file_path)),
                mustexist=False
            )

            if output_dir:
                # Save output directory for next time
                self.settings["output_dir"] = output_dir
                save_settings(self.settings)

                self.convert_file(file_path, output_dir)
            else:
                # User cancelled
                messagebox.showinfo("Cancelled", "No output folder selected.")

    @staticmethod
    def is_encrypted(file_path):
        """Check if file is 7z encrypted (password-protected CherryTree)"""
        try:
            with open(file_path, 'rb') as f:
                # 7z files start with '7z' magic bytes
                magic = f.read(2)
                return magic == b'7z'
        except:
            return False

    @staticmethod
    def decrypt_archive(file_path, password):
        """Decrypt password-protected .ctz/.ctx file, return path to extracted file"""
        if not HAS_PY7ZR:
            raise ImportError("py7zr is required for password-protected files. Install with: pip install py7zr")

        temp_dir = tempfile.mkdtemp()
        try:
            with py7zr.SevenZipFile(file_path, mode='r', password=password) as archive:
                archive.extractall(path=temp_dir)

            # Find the data file in extracted files (SQLite or XML)
            for f in os.listdir(temp_dir):
                extracted_path = os.path.join(temp_dir, f)
                if os.path.isfile(extracted_path):
                    return extracted_path, temp_dir

            raise ValueError("No data file found in encrypted archive")
        except py7zr.exceptions.PasswordRequired:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise ValueError("Password required")
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    def parse_sqlite_file(self, db_path):
        """Parse CherryTree SQLite format and return nodes dict, children_map, and images"""
        nodes = {}
        children_map = {}
        images = {}  # node_id -> list of (offset, image_data)

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # Get column info
            cursor.execute("PRAGMA table_info(node)")
            columns = [col[1] for col in cursor.fetchall()]

            # Get all nodes
            cursor.execute("SELECT * FROM node")
            for row in cursor.fetchall():
                node_data = dict(zip(columns, row))
                nodes[node_data['node_id']] = node_data

            # Get hierarchy
            cursor.execute("SELECT node_id, father_id, sequence FROM children ORDER BY sequence")
            for row in cursor.fetchall():
                node_id, father_id, _ = row
                if father_id not in children_map:
                    children_map[father_id] = []
                children_map[father_id].append(node_id)

            # Get images
            try:
                cursor.execute("SELECT node_id, offset, png FROM image ORDER BY node_id, offset")
                for row in cursor.fetchall():
                    node_id, offset, png_data = row
                    if png_data:
                        if node_id not in images:
                            images[node_id] = []
                        images[node_id].append((offset, png_data))
            except sqlite3.OperationalError:
                # No image table exists
                pass

        return nodes, children_map, images

    @staticmethod
    def get_file_type(file_path):
        """Detect if file is SQLite or XML format"""
        try:
            with open(file_path, 'rb') as f:
                magic = f.read(16)
                if magic.startswith(b'SQLite format 3'):
                    return 'sqlite'
                elif magic.startswith(b'<?xml') or magic.startswith(b'<cherrytree'):
                    return 'xml'
                else:
                    return 'unknown'
        except:
            return 'unknown'

    def parse_xml_file(self, xml_path):
        """Parse CherryTree XML format and return nodes dict, children_map, and images"""
        tree = ET.parse(xml_path)
        root = tree.getroot()

        nodes = {}
        children_map = {0: []}  # 0 is root
        images = {}  # node_id -> list of (offset, image_data)
        node_id_counter = [1]  # Use list for mutable counter in nested function

        def parse_node(element, parent_id=0):
            node_id = node_id_counter[0]
            node_id_counter[0] += 1

            # Get node name
            name = element.get('name', 'untitled')

            # Get text content from rich_text elements
            content_parts = []
            for rich_text in element.findall('rich_text'):
                if rich_text.text:
                    content_parts.append(rich_text.text)
            content = ''.join(content_parts)

            # Get images (encoded_png elements)
            node_images = []
            for encoded_png in element.findall('encoded_png'):
                char_offset = int(encoded_png.get('char_offset', 0))
                png_base64 = encoded_png.text
                if png_base64:
                    try:
                        png_data = base64.b64decode(png_base64)
                        node_images.append((char_offset, png_data))
                    except Exception:
                        pass
            if node_images:
                images[node_id] = sorted(node_images, key=lambda x: x[0])

            # Get syntax
            syntax = element.get('prog_lang', 'plain-text')
            if syntax == 'custom-colors':
                syntax = 'plain-text'

            nodes[node_id] = {
                'node_id': node_id,
                'name': name,
                'txt': content,
                'syntax': syntax
            }

            # Add to parent's children
            if parent_id not in children_map:
                children_map[parent_id] = []
            children_map[parent_id].append(node_id)

            # Process child nodes
            for child in element.findall('node'):
                parse_node(child, node_id)

        # Parse all top-level nodes
        for node_elem in root.findall('node'):
            parse_node(node_elem, 0)

        return nodes, children_map, images

    @staticmethod
    def clean_xml_content(content):
        content = re.sub(r'<\?xml.*?\?>', '', content)
        content = re.sub(r'<node.*?>', '', content)
        content = re.sub(r'</node>', '', content)
        content = re.sub(r'<rich_text.*?>', '', content)
        content = re.sub(r'</rich_text>', '', content)
        return content

    @staticmethod
    def sanitize_filename(name):
        """Make filename safe for filesystem"""
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
        return safe.strip() or "untitled"

    def convert_content(self, content, syntax):
        """Convert CherryTree content to Markdown"""
        if not content:
            return ""

        # Clean XML
        content = self.clean_xml_content(content)

        # Handle attributes
        content = re.sub(r' weight="heavy"', '', content)

        # Handle links
        link_pattern = r' link="webs ([^"]+)"'
        for match in re.finditer(link_pattern, content):
            url = match.group(1)
            content = content.replace(match.group(0), '')

        # Convert HTML entities
        content = content.replace("&lt;", "<").replace("&gt;", ">")
        content = content.replace("&amp;", "&")

        # Normalize line breaks
        content = content.replace("\r\n", "\n").replace("\r", "\n")

        if syntax != 'plain':
            # Convert HTML tags to Markdown
            content = content.replace("<b>", "**").replace("</b>", "**")
            content = content.replace("<i>", "_").replace("</i>", "_")
            content = content.replace("<code>", "`").replace("</code>", "`")
            content = content.replace("<s>", "~~").replace("</s>", "~~")
            content = content.replace("<ul>", "\n").replace("</ul>", "\n")
            content = content.replace("<ol>", "\n").replace("</ol>", "\n")
            content = content.replace("<li>", "* ").replace("</li>", "\n")
            content = content.replace("<p>", "").replace("</p>", "\n\n")
            content = content.replace("<br/>", "\n").replace("<br>", "\n")

        return content.strip()

    def convert_file(self, input_path, output_dir):
        temp_dir = None
        data_path = input_path
        file_type = None

        try:
            # Check if file is password-protected (7z encrypted)
            if self.is_encrypted(input_path):
                if not HAS_PY7ZR:
                    messagebox.showerror(
                        "Missing dependency",
                        "This file is password-protected.\n\n"
                        "Install py7zr to support encrypted files:\n"
                        "pip install py7zr"
                    )
                    return

                # Ask for password
                password = simpledialog.askstring(
                    "Password required",
                    "Enter password for encrypted CherryTree file:",
                    show='*'
                )

                if not password:
                    messagebox.showinfo("Cancelled", "No password provided.")
                    return

                try:
                    data_path, temp_dir = self.decrypt_archive(input_path, password)
                except ValueError as e:
                    messagebox.showerror("Decryption failed", str(e))
                    return

            # Detect file type
            file_type = self.get_file_type(data_path)

            # Create output directory
            os.makedirs(output_dir, exist_ok=True)

            # Parse based on file type
            if file_type == 'xml':
                nodes, children_map, images = self.parse_xml_file(data_path)
            elif file_type == 'sqlite':
                nodes, children_map, images = self.parse_sqlite_file(data_path)
            else:
                messagebox.showerror("Error", f"Unknown file format: {data_path}")
                return

            # Create attachments folder for images (Obsidian convention)
            # Images go to <vault>/obsidian/attachments/ (sibling to output folder)
            vault_root = os.path.dirname(output_dir)
            attachments_dir = os.path.join(vault_root, "obsidian", "attachments")
            if images:
                os.makedirs(attachments_dir, exist_ok=True)

            stats = {"created": 0, "skipped_empty": 0, "folders": 0, "images": 0}
            image_counter = [0]  # Mutable counter for unique image names

            def has_content(node_id):
                """Check if node or any descendant has content after conversion"""
                node = nodes.get(node_id)
                if node:
                    raw_content = node.get('txt', '')
                    if raw_content:
                        converted = self.convert_content(raw_content, node.get('syntax', 'plain'))
                        if converted and converted.strip():
                            return True
                # Also check if node has images
                if node_id in images:
                    return True
                for child_id in children_map.get(node_id, []):
                    if has_content(child_id):
                        return True
                return False

            def save_node_images(node_id, node_name):
                """Save images for a node and return list of image references"""
                if node_id not in images:
                    return []

                image_refs = []
                safe_node_name = self.sanitize_filename(node_name)

                for idx, (offset, png_data) in enumerate(images[node_id]):
                    image_counter[0] += 1
                    # Create unique filename: nodename_img1.png, nodename_img2.png, etc.
                    image_filename = f"{safe_node_name}_img{idx + 1}.png"
                    image_path = os.path.join(attachments_dir, image_filename)

                    # Handle duplicate filenames
                    if os.path.exists(image_path):
                        image_filename = f"{safe_node_name}_{image_counter[0]}_img{idx + 1}.png"
                        image_path = os.path.join(attachments_dir, image_filename)

                    with open(image_path, 'wb') as f:
                        f.write(png_data)

                    stats["images"] += 1
                    image_refs.append(f"![[{image_filename}]]")

                return image_refs

            def export_node(node_id, path=""):
                """Export node and children recursively"""
                node = nodes.get(node_id)
                if not node:
                    return

                name = node.get('name', 'untitled')
                content = node.get('txt', '')
                syntax = node.get('syntax', 'plain')
                safe_name = self.sanitize_filename(name)

                node_children = children_map.get(node_id, [])

                # Convert content first, then check if it's empty
                converted = self.convert_content(content, syntax) if content else ''
                has_text = bool(converted and converted.strip())

                # Get images for this node
                image_refs = save_node_images(node_id, name)
                has_images = bool(image_refs)

                if node_children:
                    # Node has children - create folder
                    folder_path = os.path.join(output_dir, path, safe_name)
                    os.makedirs(folder_path, exist_ok=True)
                    stats["folders"] += 1

                    # Only create .md if this node has actual content or images
                    if has_text or has_images:
                        file_path = os.path.join(folder_path, f"{safe_name}.md")
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(f"# {name}\n\n")
                            if converted:
                                f.write(converted)
                            if has_images:
                                if converted:
                                    f.write("\n\n")
                                f.write("\n\n".join(image_refs))
                        stats["created"] += 1
                    else:
                        stats["skipped_empty"] += 1

                    # Export children
                    for child_id in node_children:
                        export_node(child_id, os.path.join(path, safe_name))
                else:
                    # Leaf node - create file only if has content or images
                    if has_text or has_images:
                        folder_path = os.path.join(output_dir, path)
                        os.makedirs(folder_path, exist_ok=True)
                        file_path = os.path.join(folder_path, f"{safe_name}.md")
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(f"# {name}\n\n")
                            if converted:
                                f.write(converted)
                            if has_images:
                                if converted:
                                    f.write("\n\n")
                                f.write("\n\n".join(image_refs))
                        stats["created"] += 1
                    else:
                        stats["skipped_empty"] += 1

            # Export from root nodes (father_id = 0)
            for node_id in children_map.get(0, []):
                export_node(node_id)

            msg = (f"Conversion complete!\n\n"
                   f"Files created: {stats['created']}\n"
                   f"Folders created: {stats['folders']}\n"
                   f"Images exported: {stats['images']}\n"
                   f"Empty nodes skipped: {stats['skipped_empty']}\n\n"
                   f"Output: {output_dir}")

            messagebox.showinfo("Success", msg)

            if messagebox.askyesno("Open folder", "Open the output folder?"):
                os.system(f'open "{output_dir}"')

        except Exception as e:
            messagebox.showerror("Error", f"Conversion error:\n{str(e)}")

        finally:
            # Clean up temp directory if used
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    CTB2MD()

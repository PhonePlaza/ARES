"""
APK Management Router
Handles upload, analyze, list, delete, load decompiled APKs.
"""
import os
import re
import shutil
import subprocess
from datetime import datetime
from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel
from routers.state import analyzer

router = APIRouter(tags=["apk"])


# ============ Request Models ============

class DeleteApkRequest(BaseModel):
    folder_name: str
    package_name: str = None
    uninstall: bool = True


class LoadApkRequest(BaseModel):
    folder_name: str


# ============ Utility Functions ============

def extract_class_names_from_error(error: str) -> list:
    """
    Extract class names from Frida error messages.
    Examples:
    - "com.ad2001.frida0x3.MainActivity$1" 
    - "cannot set property 'implementation' of undefined"
    """
    patterns = [
        r'(com\.[a-zA-Z0-9_.]+\$?\d*)',  # com.package.Class or com.package.Class$1
        r'Java\.use\(["\']([^"\']+)["\']\)',  # Java.use('com.example.Class')
        r'(\w+\.\w+(?:\$\d+)?)',  # Simple Class.method or Class$1
    ]
    
    classes = set()
    for pattern in patterns:
        matches = re.findall(pattern, error)
        for match in matches:
            if match and '.' in match and not match.startswith('android.') and not match.startswith('java.'):
                classes.add(match)
    
    return list(classes)


def find_class_in_decompiled(class_name: str, apk_folder: str) -> str:
    """
    Find and read a decompiled Java class file.
    class_name: "com.ad2001.frida0x3.MainActivity$1"
    Returns: Java source code or empty string
    """
    if not apk_folder or not class_name:
        return ""
    
    # Convert class name to file path
    # com.ad2001.frida0x3.MainActivity$1 -> sources/com/ad2001/frida0x3/MainActivity.java
    base_class = class_name.split('$')[0]  # Remove inner class suffix
    file_path = base_class.replace('.', '/')
    full_path = os.path.join("temp", apk_folder, "sources", f"{file_path}.java")
    
    try:
        if os.path.exists(full_path):
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                return content[:5000]  # Limit to 5KB
    except Exception as e:
        print(f"Error reading class file: {e}")
    
    return ""


def build_file_tree(path, base_path):
    """Recursively build file tree for decompiled APK."""
    items = []
    try:
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            rel = os.path.relpath(full, base_path)
            if os.path.isdir(full):
                items.append({
                    "name": name,
                    "type": "dir",
                    "path": rel,
                    "children": build_file_tree(full, base_path)
                })
            else:
                items.append({
                    "name": name,
                    "type": "file",
                    "path": rel
                })
    except Exception as e:
        print(f"Error reading {path}: {e}")
    return items


# ============ Endpoints ============

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Uploads an APK file and creates a temp path."""
    safe_filename = file.filename.replace(" ", "_")
    file_location = f"temp/{safe_filename}"
    os.makedirs("temp", exist_ok=True)
    with open(file_location, "wb+") as file_object:
        file_object.write(file.file.read())
    
    return {
        "info": f"file '{safe_filename}' saved at '{file_location}'", 
        "path": file_location, 
        "filename": safe_filename
    }


@router.post("/api/analyze")
async def analyze_apk(data: dict):
    """
    Triggers full APK analysis on a previously uploaded file.
    Payload: { "filename": "app.apk" }
    """
    filename = data.get("filename")
    if not filename:
        return {"error": "Filename required"}
    
    apk_path = f"temp/{filename}"
    result = analyzer.decompile(apk_path)
    return result


@router.get("/api/apks/list")
async def list_decompiled_apks():
    """Lists all decompiled APKs in the temp folder with metadata."""
    apks = []
    temp_dir = "temp"
    
    if not os.path.exists(temp_dir):
        return {"apks": []}
    
    for folder_name in os.listdir(temp_dir):
        folder_path = os.path.join(temp_dir, folder_name)
        if os.path.isdir(folder_path):
            # Try to extract package name from manifest
            package_name = folder_name
            manifest_path = os.path.join(folder_path, "resources", "AndroidManifest.xml")
            if not os.path.exists(manifest_path):
                manifest_path = os.path.join(folder_path, "AndroidManifest.xml")
            
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest_content = f.read()
                        match = re.search(r'package="([^"]+)"', manifest_content)
                        if match:
                            package_name = match.group(1)
                except:
                    pass
            
            # Get folder size and modification time
            total_size = 0
            file_count = 0
            for dirpath, dirnames, filenames in os.walk(folder_path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.exists(fp):
                        total_size += os.path.getsize(fp)
                        file_count += 1
            
            # Get modification time
            mod_time = os.path.getmtime(folder_path)
            mod_date = datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M")
            
            apks.append({
                "name": folder_name,
                "package": package_name,
                "size_mb": round(total_size / (1024 * 1024), 2),
                "file_count": file_count,
                "modified": mod_date,
                "path": folder_path
            })
    
    # Sort by modification time (newest first)
    apks.sort(key=lambda x: x["modified"], reverse=True)
    return {"apks": apks}


@router.post("/api/apks/delete")
async def delete_decompiled_apk(data: DeleteApkRequest):
    """Deletes a decompiled APK folder and optionally uninstalls the app from device."""
    folder_name = data.folder_name
    package_name = data.package_name
    should_uninstall = data.uninstall
    
    if not folder_name:
        return {"status": "error", "message": "folder_name required"}
    
    folder_path = os.path.join("temp", folder_name)
    
    # Delete folder
    if os.path.exists(folder_path):
        try:
            shutil.rmtree(folder_path)
        except Exception as e:
            return {"status": "error", "message": f"Failed to delete folder: {e}"}
    else:
        return {"status": "error", "message": "Folder not found"}
    
    # Uninstall app from device if requested
    uninstall_result = None
    if should_uninstall and package_name:
        try:
            result = subprocess.run(
                ["adb", "uninstall", package_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            uninstall_result = result.stdout.strip() or result.stderr.strip()
        except Exception as e:
            uninstall_result = f"Uninstall failed: {e}"
    
    return {
        "status": "deleted",
        "folder": folder_name,
        "uninstall_result": uninstall_result
    }


@router.post("/api/apks/load")
async def load_decompiled_apk(data: LoadApkRequest):
    """Loads an existing decompiled APK folder without re-running decompilation."""
    folder_name = data.folder_name
    if not folder_name:
        return {"error": "folder_name required"}
    
    folder_path = os.path.join("temp", folder_name)
    
    if not os.path.exists(folder_path):
        return {"error": f"Folder not found: {folder_name}"}
    
    file_tree = build_file_tree(folder_path, folder_path)
    
    # Try to read manifest
    manifest_xml = ""
    manifest_path = os.path.join(folder_path, "resources", "AndroidManifest.xml")
    if not os.path.exists(manifest_path):
        manifest_path = os.path.join(folder_path, "AndroidManifest.xml")
    
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_xml = f.read()
        except:
            pass
    
    # Extract package name from manifest
    package_name = folder_name
    if manifest_xml:
        match = re.search(r'package="([^"]+)"', manifest_xml)
        if match:
            package_name = match.group(1)
    
    return {
        "file_tree": file_tree,
        "manifest_xml": manifest_xml,
        "package_name": package_name,
        "folder_name": folder_name
    }


@router.post("/api/analyze/file")
async def get_analyzed_file_content(data: dict):
    """
    Reads a specific file from the decompiled output.
    Payload: { "apk_name": "app.apk", "file_path": "sources/com/..." }
    """
    apk_name = data.get("apk_name")
    file_path = data.get("file_path")
    
    if not apk_name or not file_path:
        return {"error": "Missing apk_name or file_path"}
    
    safe_apk_name = apk_name.replace(" ", "_").replace(".apk", "")
    
    # Security check: Prevent directory traversal
    if ".." in file_path:
        return {"error": "Invalid file path"}
        
    full_path = os.path.join("temp", safe_apk_name, file_path)
    
    if not os.path.exists(full_path):
        return {"error": f"File not found: {full_path}"}
        
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        return {"error": f"Read error: {str(e)}"}

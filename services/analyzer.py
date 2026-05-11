"""
APKAnalyzer - Decompiles Android APK files and extracts metadata.
Uses JADX for decompilation, parses AndroidManifest.xml, and builds a file tree for the frontend.
"""

import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, List


class APKAnalyzer:
    """Analyzes APK files: decompile, parse manifest, build file tree."""
    
    def __init__(self, temp_dir: str = "temp"):
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(exist_ok=True)
        self.jadx_path = shutil.which("jadx")
        
        if not self.jadx_path:
            self.jadx_path = "jadx.bat" if os.name == 'nt' else "jadx"

    def decompile(self, apk_path: str) -> Dict[str, Any]:
        """
        Decompile an APK file into source code using JADX.
        Returns manifest info, file tree, and output directory on success.
        """
        if not os.path.exists(apk_path):
            return {"error": "APK file not found"}

        apk_name = Path(apk_path).stem
        output_dir = self.temp_dir / apk_name
        
        if output_dir.exists():
            try:
                shutil.rmtree(output_dir)
            except PermissionError as e:
                print(f"[WARNING] Cannot clean old output: {e}")
        
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            cmd = [self.jadx_path, "-d", str(output_dir), str(apk_path)]
            print(f"[DEBUG] Running command: {cmd}")
            
            use_shell = os.name == 'nt'
            
            process = subprocess.run(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True, 
                shell=use_shell,
                timeout=300
            )
            
            print(f"[DEBUG] Return Code: {process.returncode}")
            print(f"[DEBUG] STDOUT: {process.stdout}")
            print(f"[DEBUG] STDERR: {process.stderr}")
            
            if process.returncode != 0:
                print(f"[DEBUG] Jadx finished with non-zero exit code: {process.returncode}")
                
                manifest_check_path = output_dir / "resources" / "AndroidManifest.xml"
                if not manifest_check_path.exists():
                     manifest_check_path = output_dir / "AndroidManifest.xml"
                
                if not manifest_check_path.exists():
                    details = f"STDERR: {process.stderr}\nSTDOUT: {process.stdout}"
                    return {
                        "error": "Jadx decompilation failed (No Manifest found)", 
                        "details": details
                    }
                else:
                    print("[WARNING] Jadx reported errors but Manifest was found. Proceeding...")

            manifest_info = self._parse_manifest(output_dir)
            file_tree = self._build_file_tree(output_dir)
            
            return {
                "success": True,
                "package_name": manifest_info.get("package", "unknown"),
                "manifest_xml": manifest_info.get("raw_xml", ""),
                "dataset": manifest_info,
                "file_tree": file_tree,
                "output_dir": str(output_dir),
                "warnings": f"Jadx finished with errors: {process.stdout[-200:]}" if process.returncode != 0 else None
            }

        except Exception as e:
            return {"error": str(e)}

    def _parse_manifest(self, root_dir: Path) -> Dict[str, Any]:
        """Parse AndroidManifest.xml and extract package info, permissions, components."""
        manifest_path = root_dir / "resources" / "AndroidManifest.xml"
        if not manifest_path.exists():
            manifest_path = root_dir / "AndroidManifest.xml"
        
        if not manifest_path.exists():
            return {"error": "AndroidManifest.xml not found"}

        try:
            tree = ET.parse(manifest_path)
            root = tree.getroot()
            
            ns = {'android': 'http://schemas.android.com/apk/res/android'}
            
            package = root.get('package')
            
            permissions = [
                name for elem in root.findall('uses-permission')
                if (name := elem.get(f"{{{ns['android']}}}name"))
            ]
            
            activities = [
                name for elem in root.findall('application/activity')
                if (name := elem.get(f"{{{ns['android']}}}name"))
            ]
            
            services = [
                name for elem in root.findall('application/service')
                if (name := elem.get(f"{{{ns['android']}}}name"))
            ]
            
            receivers = [
                name for elem in root.findall('application/receiver')
                if (name := elem.get(f"{{{ns['android']}}}name"))
            ]
            
            providers = [
                name for elem in root.findall('application/provider')
                if (name := elem.get(f"{{{ns['android']}}}name"))
            ]

            with open(manifest_path, "r", encoding="utf-8") as f:
                raw_xml = f.read()

            return {
                "package": package,
                "permissions": permissions,
                "activities": activities,
                "services": services,
                "receivers": receivers,
                "providers": providers,
                "raw_xml": raw_xml
            }
        except Exception as e:
            return {"error": f"Manifest Parse Error: {e}"}

    def _build_file_tree(self, root_dir: Path) -> List[Dict[str, Any]]:
        """Build a recursive file tree structure for the frontend file explorer."""
        def scandir_recursive(path: Path):
            items = []
            try:
                for entry in os.scandir(path):
                    if entry.is_dir():
                        items.append({
                            "name": entry.name,
                            "type": "dir",
                            "children": scandir_recursive(Path(entry.path)),
                            "path": str(Path(entry.path).relative_to(root_dir))
                        })
                    else:
                        items.append({
                            "name": entry.name,
                            "type": "file",
                            "path": str(Path(entry.path).relative_to(root_dir))
                        })
            except Exception:
                pass
            
            return sorted(items, key=lambda x: (x['type'] != 'dir', x['name']))

        return scandir_recursive(root_dir)

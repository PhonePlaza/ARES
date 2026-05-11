"""
NativeAnalyzer - Analyzes native .so files inside Android APKs.
Detects System.loadLibrary() calls, locates .so files from JADX output,
performs automated reconnaissance with r2pipe, and generates Frida scripts from tested templates.
"""

import os
import re
import glob
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple, Optional

try:
    import r2pipe
    R2PIPE_AVAILABLE = True
except ImportError:
    R2PIPE_AVAILABLE = False
    print("[WARNING] r2pipe not installed. Native analysis will be unavailable.")


class NativeAnalyzer:
    """Analyzes native .so files: detect, recon, disassemble, and generate Frida hooks."""

    def __init__(self, temp_dir: str = "temp"):
        self.temp_dir = Path(temp_dir)
        self.arch_priority = ["x86_64", "x86", "arm64-v8a", "armeabi-v7a"]

    def adb_recon_app_data(self, package_name: str) -> str:
        """Explore app's /data/data/{package}/ via ADB shell for recon."""
        recon = []
        base_path = f"/data/data/{package_name}"
        
        try:
            # List top-level app data directory
            result = subprocess.run(
                ["adb", "shell", "ls", "-la", base_path],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                recon.append(f"=== {base_path} ===")
                recon.append(result.stdout.strip())
                
                # Explore shared_prefs if exists
                prefs_result = subprocess.run(
                    ["adb", "shell", "ls", "-la", f"{base_path}/shared_prefs/"],
                    capture_output=True, text=True, timeout=5
                )
                if prefs_result.returncode == 0 and prefs_result.stdout.strip():
                    recon.append(f"\n=== {base_path}/shared_prefs/ ===")
                    recon.append(prefs_result.stdout.strip())
                    
                    # Read each XML file (small files only)
                    for line in prefs_result.stdout.strip().split("\n"):
                        if ".xml" in line:
                            filename = line.split()[-1] if line.split() else ""
                            if filename.endswith(".xml"):
                                cat_result = subprocess.run(
                                    ["adb", "shell", "cat", f"{base_path}/shared_prefs/{filename}"],
                                    capture_output=True, text=True, timeout=5
                                )
                                if cat_result.returncode == 0 and len(cat_result.stdout) < 5000:
                                    recon.append(f"\n=== cat {filename} ===")
                                    recon.append(cat_result.stdout.strip())
                
                # Explore databases if exists
                db_result = subprocess.run(
                    ["adb", "shell", "ls", "-la", f"{base_path}/databases/"],
                    capture_output=True, text=True, timeout=5
                )
                if db_result.returncode == 0 and db_result.stdout.strip():
                    recon.append(f"\n=== {base_path}/databases/ ===")
                    recon.append(db_result.stdout.strip())
                    
        except Exception as e:
            recon.append(f"[ADB RECON] Error: {e}")
        
        result_text = "\n".join(recon)
        if result_text:
            print(f"[ADB RECON] Collected {len(recon)} entries for {package_name}")
        return result_text


    # Framework libraries to skip — NOT developer code
    SKIP_LIBS = {"flutter", "app_flutter"}

    def detect_native_libs(self, apk_folder: str) -> List[Dict]:
        """
        Scan all .java files in decompiled sources for System.loadLibrary() calls.
        Detects Flutter apps: skips libflutter.so, adds libapp.so (AOT Dart business logic).
        """
        sources_dir = self.temp_dir / apk_folder / "sources"
        
        if not sources_dir.exists():
            print(f"[NATIVE] Sources directory not found: {sources_dir}")
            return []

        detected_libs = []
        seen_names = set()
        is_flutter = False

        pattern = re.compile(r'System\.loadLibrary\s*\(\s*"([^"]+)"\s*\)')

        for java_file in sources_dir.rglob("*.java"):
            try:
                with open(java_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                matches = pattern.findall(content)
                for lib_name in matches:
                    if lib_name not in seen_names:
                        seen_names.add(lib_name)
                        
                        if lib_name == "flutter":
                            is_flutter = True
                            print(f'[NATIVE] ⚠️ Flutter app detected — skipping libflutter.so (framework engine)')
                            continue
                        
                        if lib_name in self.SKIP_LIBS:
                            print(f'[NATIVE] Skipping framework lib: lib{lib_name}.so')
                            continue
                        
                        detected_libs.append({
                            "name": lib_name,
                            "so_file": f"lib{lib_name}.so",
                            "found_in": java_file.name
                        })
                        print(f'[NATIVE] Found System.loadLibrary("{lib_name}") in {java_file.name}')
            
            except Exception as e:
                continue

        # Flutter: libapp.so has AOT-compiled Dart business logic
        if is_flutter:
            apk_path = self.temp_dir / apk_folder
            for libapp in apk_path.rglob("libapp.so"):
                if "app" not in seen_names:
                    seen_names.add("app")
                    detected_libs.append({
                        "name": "app",
                        "so_file": "libapp.so",
                        "found_in": str(libapp.relative_to(apk_path)),
                        "is_flutter_app": True
                    })
                    print(f'[NATIVE] Found libapp.so (Flutter AOT business logic)')
                    break
            for lib in detected_libs:
                lib["flutter_app"] = True

        return detected_libs


    def find_so_file(self, apk_folder: str, so_filename: str) -> Optional[str]:
        """
        Locate a .so file from JADX output, searching by architecture priority.
        Path format: temp/<apk>/resources/lib/<arch>/<so_filename>
        """
        lib_base = self.temp_dir / apk_folder / "resources" / "lib"

        if not lib_base.exists():
            print(f"[NATIVE] lib directory not found: {lib_base}")
            return None

        for arch in self.arch_priority:
            so_path = lib_base / arch / so_filename
            if so_path.exists():
                print(f"[NATIVE] Found .so: {so_path} (arch: {arch})")
                return str(so_path.resolve())

        for arch_dir in lib_base.iterdir():
            if arch_dir.is_dir():
                so_path = arch_dir / so_filename
                if so_path.exists():
                    print(f"[NATIVE] Found .so (fallback): {so_path}")
                    return str(so_path.resolve())

        print(f"[NATIVE] .so not found: {so_filename}")
        return None


    def auto_r2_recon(self, so_file_path: str) -> Tuple[str, List[str]]:
        """
        Automated reconnaissance on .so file using r2pipe.
        Returns (recon_report_text, jni_function_names_list).
        """
        if not R2PIPE_AVAILABLE:
            return ("[ERROR] r2pipe not installed. Run: pip install r2pipe", [])

        print(f"[NATIVE] Starting r2 recon on: {so_file_path}")

        try:
            r2 = r2pipe.open(so_file_path)
            r2.cmd("aaa")

            recon_report = "=== 🔍 ARES Native Reconnaissance Report ===\n\n"

            # JNI Functions
            jni_funcs = []
            try:
                exports = r2.cmdj("iEj") or []
                jni_funcs = [
                    ex['name'] for ex in exports 
                    if 'name' in ex and 'Java_' in ex['name']
                ]
                if jni_funcs:
                    recon_report += f"## 1. JNI Functions Found ({len(jni_funcs)}):\n"
                    for func in jni_funcs:
                        recon_report += f"  - {func}\n"
                else:
                    recon_report += "## 1. JNI Functions: None found in exports\n"
            except Exception as e:
                recon_report += f"## 1. JNI Functions: Error - {e}\n"

            # Interesting Strings
            try:
                strings = r2.cmdj("izj") or []
                interesting_strings = [
                    s.get('string', '') for s in strings
                    if s.get('size', 0) > 4 and s.get('string', '')
                ]
                display_strings = interesting_strings[:15]
                recon_report += f"\n## 2. Interesting Strings ({len(interesting_strings)} total, showing top {len(display_strings)}):\n"
                for s in display_strings:
                    recon_report += f'  - "{s}"\n'
            except Exception as e:
                recon_report += f"\n## 2. Strings: Error - {e}\n"

            # Suspicious Functions
            try:
                functions = r2.cmdj("aflj") or []
                suspicious_keywords = [
                    'strcmp', 'strncmp', 'memcmp',
                    'ptrace',
                    'dlopen', 'dlsym',
                    'encrypt', 'decrypt', 'aes', 'des',
                    'base64', 'md5', 'sha',
                    'fopen', 'fread', 'fwrite',
                    'connect', 'send', 'recv',
                    '__android_log',
                ]
                sus_funcs = [
                    f['name'] for f in functions
                    if any(kw in f.get('name', '').lower() for kw in suspicious_keywords)
                ]
                recon_report += f"\n## 3. Suspicious Functions ({len(sus_funcs)}):\n"
                for func in sus_funcs[:20]:
                    recon_report += f"  - {func}\n"
                if not sus_funcs:
                    recon_report += "  - None detected\n"
            except Exception as e:
                recon_report += f"\n## 3. Suspicious Functions: Error - {e}\n"

            # Binary Info
            try:
                info = r2.cmdj("ij") or {}
                bin_info = info.get("bin", {})
                recon_report += f"\n## 4. Binary Info:\n"
                recon_report += f"  - Architecture: {bin_info.get('arch', 'unknown')}\n"
                recon_report += f"  - Bits: {bin_info.get('bits', 'unknown')}\n"
                recon_report += f"  - OS: {bin_info.get('os', 'unknown')}\n"
                recon_report += f"  - Stripped: {bin_info.get('stripped', 'unknown')}\n"
            except Exception as e:
                recon_report += f"\n## 4. Binary Info: Error - {e}\n"

            r2.quit()

            print(f"[NATIVE] Recon complete. Found {len(jni_funcs)} JNI functions")
            return (recon_report, jni_funcs)

        except Exception as e:
            error_msg = f"[ERROR] r2pipe analysis failed: {str(e)}"
            print(error_msg)
            return (error_msg, [])


    def extract_function_data(self, so_file_path: str, func_name: str) -> Dict:
        """
        Extract disassembly and control flow graph for a target function.
        Returns dict with name, disasm, cfg_summary, and size.
        """
        if not R2PIPE_AVAILABLE:
            return {"name": func_name, "error": "r2pipe not installed"}

        try:
            r2 = r2pipe.open(so_file_path)
            r2.cmd("aaa")
            r2.cmd(f"s {func_name}")

            result = {
                "name": func_name,
                "disasm": "",
                "cfg_summary": "",
                "size": 0
            }

            # Disassembly
            try:
                pdf_data = r2.cmdj("pdfj")
                if pdf_data and 'ops' in pdf_data:
                    result["size"] = pdf_data.get("size", 0)
                    
                    lines = []
                    for op in pdf_data['ops'][:300]:
                        addr = hex(op.get('offset', 0))
                        disasm = op.get('disasm', '???')
                        lines.append(f"  {addr}:  {disasm}")
                    
                    result["disasm"] = "\n".join(lines)
                    
                    if len(pdf_data['ops']) > 300:
                        result["disasm"] += f"\n  ... (truncated, {len(pdf_data['ops'])} total instructions)"
                else:
                    result["disasm"] = "// Could not disassemble function"
            except Exception as e:
                result["disasm"] = f"// Disassembly error: {e}"

            # CFG Summary
            try:
                cfg_data = r2.cmdj("agj")
                if cfg_data and len(cfg_data) > 0:
                    graph = cfg_data[0]
                    blocks = graph.get("blocks", [])
                    
                    total_blocks = len(blocks)
                    total_edges = sum(
                        (1 if b.get("jump") else 0) + (1 if b.get("fail") else 0) 
                        for b in blocks
                    )
                    
                    cfg_lines = [f"CFG: {total_blocks} blocks, {total_edges} edges"]
                    for i, block in enumerate(blocks[:10]):
                        offset = hex(block.get("offset", 0))
                        size = block.get("size", 0)
                        jump = hex(block["jump"]) if block.get("jump") else "none"
                        fail = hex(block["fail"]) if block.get("fail") else "none"
                        cfg_lines.append(
                            f"  Block {i}: {offset} (size={size}) → jump={jump}, fail={fail}"
                        )
                    
                    if total_blocks > 10:
                        cfg_lines.append(f"  ... ({total_blocks - 10} more blocks)")
                    
                    result["cfg_summary"] = "\n".join(cfg_lines)
                else:
                    result["cfg_summary"] = "// No CFG data"
            except Exception as e:
                result["cfg_summary"] = f"// CFG error: {e}"

            r2.quit()
            return result

        except Exception as e:
            return {"name": func_name, "error": str(e)}


    def format_native_prompt(self, recon_report: str, functions_data: List[Dict],
                             java_context: str = "") -> str:
        """Combine recon report + assembly + CFG + Java context into an AI prompt."""
        prompt = "## NATIVE LIBRARY ANALYSIS\n\n"
        prompt += "ARES automated reconnaissance results:\n\n"
        prompt += recon_report
        prompt += "\n\n"

        if functions_data:
            prompt += "## TARGET FUNCTION ANALYSIS\n\n"
            for i, func_data in enumerate(functions_data[:5]):
                name = func_data.get("name", "unknown")
                prompt += f"### Function {i+1}: `{name}`\n"
                
                if "error" in func_data:
                    prompt += f"Error: {func_data['error']}\n\n"
                    continue
                
                size = func_data.get("size", 0)
                prompt += f"Size: {size} bytes\n\n"
                
                disasm = func_data.get("disasm", "")
                if disasm:
                    prompt += "**Assembly:**\n```asm\n"
                    prompt += disasm
                    prompt += "\n```\n\n"
                
                cfg = func_data.get("cfg_summary", "")
                if cfg:
                    prompt += "**Control Flow Graph:**\n```\n"
                    prompt += cfg
                    prompt += "\n```\n\n"

        if java_context:
            prompt += "## DECOMPILED JAVA CONTEXT\n\n"
            prompt += "Java code calling native functions:\n"
            prompt += f"```java\n{java_context[:5000]}\n```\n\n"

        return prompt


    def run_full_analysis(self, apk_folder: str, native_libs: List[Dict],
                          java_context: str = "") -> str:
        """
        Run the full native analysis pipeline:
        1. Locate .so file
        2. r2 reconnaissance
        3. Extract function data for each JNI function
        4. Format prompt for AI
        """
        all_recon = ""
        all_functions_data = []

        for lib_info in native_libs:
            so_filename = lib_info["so_file"]
            
            so_path = self.find_so_file(apk_folder, so_filename)
            if not so_path:
                all_recon += f"\n[!] Could not find {so_filename} in decompiled output\n"
                continue

            recon_report, jni_funcs = self.auto_r2_recon(so_path)
            all_recon += recon_report + "\n"

            for func_name in jni_funcs[:5]:
                func_data = self.extract_function_data(so_path, func_name)
                all_functions_data.append(func_data)

        return self.format_native_prompt(all_recon, all_functions_data, java_context)


    def generate_native_script(self, apk_folder: str, native_libs: List[Dict]) -> str:
        """
        Generate a Frida script from tested templates (Frida 17 compatible).
        Only handles strcmp reading mode (proven pattern).
        Bypass mode is left to AI (needs code analysis for correct return value).
        """
        script_parts = []
        
        for lib_info in native_libs:
            so_filename = lib_info["so_file"]
            lib_name = lib_info["name"]
            
            so_path = self.find_so_file(apk_folder, so_filename)
            if not so_path:
                script_parts.append(f'console.log("[-] Could not find {so_filename}");')
                continue

            recon_report, jni_funcs = self.auto_r2_recon(so_path)
            
            has_strcmp = "strcmp" in recon_report.lower()
            
            clean_jni_names = []
            for func in jni_funcs:
                clean_name = func.replace("sym.", "").replace("sym.imp.", "")
                clean_jni_names.append(clean_name)

            if has_strcmp and clean_jni_names:
                # === STRATEGY: Read strcmp values (don't bypass — we want to see the flag) ===
                jni_first = clean_jni_names[0]
                jni_parts = jni_first.replace("Java_", "").split("_")
                if len(jni_parts) >= 2:
                    java_method = jni_parts[-1]
                    java_class = ".".join(jni_parts[:-1])
                else:
                    java_method = jni_first
                    java_class = ""

                lib_script = f'''
// ===== Native Hook: {so_filename} (strcmp reading mode) =====
Java.perform(() => {{
    console.log("[*] Looking for strcmp...");

    var strcmpAddr = Process.findModuleByName("libc.so")
                            .getExportByName("strcmp");

    if (!strcmpAddr) {{
        console.log("[-] strcmp not found");
        return;
    }}
    console.log("[+] Found strcmp @ " + strcmpAddr);

    var myInput = "";
'''
                if java_class:
                    lib_script += f'''
    // Hook Java side to capture user input
    var TargetClass = Java.use("{java_class}");
    TargetClass.{java_method}.implementation = function(input) {{
        myInput = input.toString();
        console.log("[*] User input: " + myInput);
        return this.{java_method}(input);  // Call original — don't bypass!
    }};
'''

                lib_script += f'''
    // Attach to strcmp — filter by user input to see compared values
    Interceptor.attach(strcmpAddr, {{
        onEnter: function(args) {{
            try {{
                var s1 = args[0].readCString();
                var s2 = args[1].readCString();
                if (myInput && (s1.indexOf(myInput) !== -1 || s2.indexOf(myInput) !== -1)) {{
                    console.log("\\n[+] --------------------------");
                    console.log("    s1: " + s1);
                    console.log("    s2: " + s2);
                    console.log("    --------------------------");
                }}
            }} catch(e) {{}}
        }}
    }});
    console.log("[+] Hooked strcmp (filtered by user input)");
}});
'''

            elif clean_jni_names:
                # === No strcmp → let AI handle bypass (it can analyze correct return value) ===
                lib_script = None

            else:
                # No JNI exports (e.g. Flutter apps) → let AI handle it
                lib_script = None

            if lib_script:
                script_parts.append(lib_script)

        return "\n".join(script_parts) if script_parts else ''

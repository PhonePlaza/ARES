"""
AI Router
Handles AI-powered script generation, healing, and refinement.
"""
import os
import re
from fastapi import APIRouter
from pydantic import BaseModel
from routers.state import ai_engine, native_analyzer
import routers.state as app_state
from routers.apk import extract_class_names_from_error, find_class_in_decompiled

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ============ Request Models ============

class HealScriptRequest(BaseModel):
    error: str
    script: str
    history: list = []  # Optional: previous healing attempts
    apk_folder: str = ""  # Optional: folder name in temp/ for context


class RefineScriptRequest(BaseModel):
    script: str
    feedback: str
    apk_folder: str = ""
    frida_logs: str = ""


# ============ Endpoints ============

@router.post("/auto-generate")
async def ai_auto_generate(data: dict):
    """
    วิเคราะห์ APK แบบอัตโนมัติ และสร้าง Frida script
    
    Frontend เรียก: หน้า /analysis กดปุ่ม "Generate Hook"
    Payload: { "apk_name": "Challenge0x8.apk" }
    
    Flow:
    1. อ่าน AndroidManifest.xml จาก APK ที่ decompile แล้ว
    2. หา Main Activity แล้วอ่าน Java source code
    3. ตรวจสอบ Native Library (.so) ด้วย native_analyzer.detect_native_libs()
    4. ถ้ามี Library → return ข้อมูลให้ Frontend แสดง popup ให้ User เลือก
       (User เลือก Deep Analysis → เรียก /native-deep-analysis)
       (User เลือก Skip → เรียก /skip-native)
    5. ถ้าไม่มี Library → ส่ง Java code ให้ AI วิเคราะห์ + สร้าง Frida script
    6. บันทึก analysis context ไว้ให้ refine_script ใช้ภายหลัง
    """
    apk_name = data.get("apk_name")
    if not apk_name:
        return {"error": "apk_name required"}
    
    # Get APK base name (without extension)
    apk_base = apk_name.replace(".apk", "")
    output_dir = f"temp/{apk_base}"
    
    if not os.path.exists(output_dir):
        return {"error": f"APK not decompiled. Directory not found: {output_dir}"}
    
    # 1. Read AndroidManifest.xml
    manifest_path = f"{output_dir}/resources/AndroidManifest.xml"
    if not os.path.exists(manifest_path):
        manifest_path = f"{output_dir}/AndroidManifest.xml"
    
    if not os.path.exists(manifest_path):
        return {"error": "AndroidManifest.xml not found"}
    
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_xml = f.read()
    
    # 2. Extract package name and main activity
    package_match = re.search(r'package="([^"]+)"', manifest_xml)
    package_name = package_match.group(1) if package_match else "unknown"
    
    # Find launcher activity (main entry point)
    main_activity = None
    activity_matches = re.findall(r'<activity[^>]*android:name="([^"]+)"[^>]*>', manifest_xml, re.DOTALL)
    
    # Look for the one with LAUNCHER category
    launcher_match = re.search(
        r'<activity[^>]*android:name="([^"]+)"[^>]*>.*?LAUNCHER.*?</activity>', 
        manifest_xml, 
        re.DOTALL
    )
    if launcher_match:
        main_activity = launcher_match.group(1)
    elif activity_matches:
        # Fallback to first activity or one containing "Main"
        for act in activity_matches:
            if "main" in act.lower():
                main_activity = act
                break
        if not main_activity and activity_matches:
            main_activity = activity_matches[0]
    
    # 3. Convert activity name to file path
    main_class_code = ""
    if main_activity:
        # Handle relative class names (e.g., ".MainActivity" -> full path)
        if main_activity.startswith("."):
            main_activity = package_name + main_activity
        
        # Convert to file path: com.example.MainActivity -> sources/com/example/MainActivity.java
        class_path = main_activity.replace(".", "/")
        source_path = f"{output_dir}/sources/{class_path}.java"
        
        if os.path.exists(source_path):
            with open(source_path, "r", encoding="utf-8", errors="ignore") as f:
                main_class_code = f.read()
        else:
            # Try to find the file
            possible_paths = [
                f"{output_dir}/sources/{class_path}.java",
                f"{output_dir}/sources/{class_path.rsplit('/', 1)[0]}/{class_path.rsplit('/', 1)[-1]}.java",
            ]
            for p in possible_paths:
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        main_class_code = f.read()
                    break
            
            if not main_class_code:
                main_class_code = f"// Could not find source file for {main_activity}"
    
    # 4. Auto-read related custom classes
    additional_classes = []
    skip_prefixes = (
        "java.", "javax.", "android.", "androidx.",
        "com.google.", "org.w3c.", "dalvik.", "kotlin.",
        "io.reactivex.", "okhttp3.", "retrofit2.",
        "com.squareup.", "org.json.",
    )
    
    # Step 1: ตาม import ไปอ่านไฟล์ (ข้าม standard library)
    if main_class_code:
        import_matches = re.findall(r'import\s+([\w.]+);', main_class_code)
        
        for imp in import_matches:
            if imp.startswith(skip_prefixes):
                continue
            
            cls_path = imp.replace(".", "/")
            cls_file = f"{output_dir}/sources/{cls_path}.java"
            
            if os.path.exists(cls_file):
                with open(cls_file, "r", encoding="utf-8", errors="ignore") as f:
                    cls_code = f.read()
                additional_classes.append(cls_code)
                print(f"[AUTO-READ] Import class: {imp}")
            
            if len(additional_classes) >= 3:
                break
    
    # Step 2: หา class ในโฟลเดอร์เดียวกัน (ใช้ในcode แต่ไม่มี import)
    if len(additional_classes) < 3 and main_class_code and main_activity:
        class_path = main_activity.replace(".", "/")
        source_path = f"{output_dir}/sources/{class_path}.java"
        main_dir = os.path.dirname(source_path)
        
        # หาชื่อ class ที่ถูกใช้ใน code เช่น new Checker(), Checker.method()
        used_classes = set(re.findall(
            r'(?:new\s+|extends\s+|implements\s+|\b)([A-Z][a-zA-Z0-9]+)\s*[.(]',
            main_class_code
        ))
        # ลบ standard Java/Android classes
        java_builtins = {"String", "Integer", "Boolean", "Object", "System",
                         "Log", "Intent", "Bundle", "View", "Toast",
                         "Context", "Activity", "Fragment", "AlertDialog",
                         "ArrayList", "HashMap", "List", "Map", "Exception",
                         "StringBuilder", "Thread", "Runnable", "Override",
                         "EditText", "Button", "TextView", "ImageView",
                         "SharedPreferences", "Arrays", "Math", "Class",
                         "Method", "Field", "Byte", "Short", "Long",
                         "Float", "Double", "Character"}
        used_classes -= java_builtins
        
        if os.path.isdir(main_dir):
            main_filename = os.path.basename(source_path)
            already_read = {main_filename}
            # เพิ่ม class ที่อ่านจาก Step 1 แล้ว
            for imp in import_matches:
                already_read.add(imp.rsplit(".", 1)[-1] + ".java")
            
            for fname in os.listdir(main_dir):
                if not fname.endswith(".java") or fname in already_read:
                    continue
                class_name = fname.replace(".java", "")
                if class_name in used_classes:
                    fpath = os.path.join(main_dir, fname)
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        cls_code = f.read()
                    additional_classes.append(cls_code)
                    already_read.add(fname)
                    print(f"[AUTO-READ] Same-package class: {class_name}")
                
                if len(additional_classes) >= 3:
                    break
    # Step 3: อ่านทุก .java ในโฟลเดอร์เดียวกัน (package เดียวกัน)
    # กรณีที่ class ไม่ได้ถูก import หรือ new โดยตรงใน MainActivity
    if len(additional_classes) < 3 and main_activity:
        class_path = main_activity.replace(".", "/")
        source_path = f"{output_dir}/sources/{class_path}.java"
        main_dir = os.path.dirname(source_path)
        main_filename = os.path.basename(source_path)

        # รวมทุก class ที่อ่านไปแล้วจากทุก step
        already_added = {"R.java", main_filename}
        already_added.update({
            imp.rsplit(".", 1)[-1] + ".java"
            for imp in (import_matches if main_class_code else [])
        })
        # เพิ่ม class ที่ Step 2 อ่านไปแล้ว (เช็คจาก content)
        already_added_content = set()
        for cls_code in additional_classes:
            first_line = cls_code.strip().split("\n")[0]
            class_match = re.search(r'class\s+(\w+)', first_line)
            if class_match:
                already_added_content.add(class_match.group(1) + ".java")
        already_added.update(already_added_content)

        if os.path.isdir(main_dir):
            for fname in os.listdir(main_dir):
                if not fname.endswith(".java") or fname in already_added:
                    continue
                fpath = os.path.join(main_dir, fname)
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    cls_code = f.read()
                additional_classes.append(cls_code)
                print(f"[AUTO-READ] Package scan: {fname}")
                if len(additional_classes) >= 3:
                    break
    if additional_classes:
        print(f"[AUTO-READ] Total additional classes found: {len(additional_classes)}")
    
    # 5. Detect native libraries
    detected_native_libs = native_analyzer.detect_native_libs(apk_base)
    
    if detected_native_libs:
        # Check if Flutter app
        is_flutter = any(lib.get("flutter_app") for lib in detected_native_libs)
        
        # Native lib found — return detection info for user to decide
        return {
            "native_detected": True,
            "flutter_detected": is_flutter,
            "native_libs": detected_native_libs,
            "package": package_name,
            "main_activity": main_activity,
            "success": False
        }
    
    # 6. No native lib — generate standard Frida script
    result = ai_engine.analyze_and_generate_hooks(
        package_name=package_name,
        manifest_xml=manifest_xml,
        main_class_code=main_class_code,
        additional_classes=additional_classes
    )
    
    # Save analysis context for refine_script to use later
    app_state.last_analysis_context = {
        "native_prompt": "",
        "java_code": main_class_code[:5000],
        "manifest_xml": manifest_xml[:3000],
        "package_name": package_name,
        "apk_name": apk_base,
    }
    
    return {
        "script": result.get("script", ""),
        "analysis": result.get("analysis", ""),
        "package": package_name,
        "main_activity": main_activity,
        "success": result.get("success", False)
    }


@router.post("/skip-native")
async def ai_skip_native(data: dict):
    """
    Skip native analysis — generate standard Frida script.
    Same as auto-generate but skips native library detection.
    Payload: { "apk_name": "app.apk" }
    """
    apk_name = data.get("apk_name")
    if not apk_name:
        return {"error": "apk_name required"}
    
    apk_base = apk_name.replace(".apk", "")
    output_dir = f"temp/{apk_base}"
    
    if not os.path.exists(output_dir):
        return {"error": f"APK not decompiled. Directory not found: {output_dir}"}
    
    # Read manifest
    manifest_path = f"{output_dir}/resources/AndroidManifest.xml"
    if not os.path.exists(manifest_path):
        manifest_path = f"{output_dir}/AndroidManifest.xml"
    if not os.path.exists(manifest_path):
        return {"error": "AndroidManifest.xml not found"}
    
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_xml = f.read()
    
    # Extract package name
    package_match = re.search(r'package="([^"]+)"', manifest_xml)
    package_name = package_match.group(1) if package_match else "unknown"
    
    # Find main activity
    main_activity = None
    launcher_match = re.search(
        r'<activity[^>]*android:name="([^"]+)"[^>]*>.*?LAUNCHER.*?</activity>', 
        manifest_xml, re.DOTALL
    )
    if launcher_match:
        main_activity = launcher_match.group(1)
    else:
        activity_matches = re.findall(r'<activity[^>]*android:name="([^"]+)"[^>]*>', manifest_xml)
        for act in activity_matches:
            if "main" in act.lower():
                main_activity = act
                break
        if not main_activity and activity_matches:
            main_activity = activity_matches[0]
    
    # Read main class code
    main_class_code = ""
    if main_activity:
        if main_activity.startswith("."):
            main_activity = package_name + main_activity
        class_path = main_activity.replace(".", "/")
        source_path = f"{output_dir}/sources/{class_path}.java"
        if os.path.exists(source_path):
            with open(source_path, "r", encoding="utf-8", errors="ignore") as f:
                main_class_code = f.read()
    
    # Generate standard Frida script (skip native detection)
    result = ai_engine.analyze_and_generate_hooks(
        package_name=package_name,
        manifest_xml=manifest_xml,
        main_class_code=main_class_code
    )
    
    return {
        "script": result.get("script", ""),
        "analysis": result.get("analysis", ""),
        "package": package_name,
        "main_activity": main_activity,
        "success": result.get("success", False)
    }


@router.post("/native-deep-analysis")
async def ai_native_deep_analysis(data: dict):
    """
    Deep analysis: r2pipe recon + AI assembly analysis + Frida script generation.
    Payload: {
        "apk_name": "Challenge0x8.apk",
        "native_libs": [{"name": "frida0x8", "so_file": "libfrida0x8.so", ...}]
    }
    """
    apk_name = data.get("apk_name")
    native_libs = data.get("native_libs", [])
    
    if not apk_name or not native_libs:
        return {"error": "apk_name and native_libs required"}
    
    apk_base = apk_name.replace(".apk", "")
    output_dir = f"temp/{apk_base}"
    
    if not os.path.exists(output_dir):
        return {"error": f"APK not decompiled. Directory not found: {output_dir}"}
    
    # Read manifest + package name
    manifest_path = f"{output_dir}/resources/AndroidManifest.xml"
    if not os.path.exists(manifest_path):
        manifest_path = f"{output_dir}/AndroidManifest.xml"
    if not os.path.exists(manifest_path):
        return {"error": "AndroidManifest.xml not found"}
    
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_xml = f.read()
    
    package_match = re.search(r'package="([^"]+)"', manifest_xml)
    package_name = package_match.group(1) if package_match else "unknown"
    
    # Find main activity + read Java source
    main_activity = None
    launcher_match = re.search(
        r'<activity[^>]*android:name="([^"]+)"[^>]*>.*?LAUNCHER.*?</activity>', 
        manifest_xml, re.DOTALL
    )
    if launcher_match:
        main_activity = launcher_match.group(1)
    
    main_class_code = ""
    if main_activity:
        if main_activity.startswith("."):
            main_activity = package_name + main_activity
        class_path = main_activity.replace(".", "/")
        source_path = f"{output_dir}/sources/{class_path}.java"
        if os.path.exists(source_path):
            with open(source_path, "r", encoding="utf-8", errors="ignore") as f:
                main_class_code = f.read()
    
    # Check if Flutter app
    is_flutter = any(lib.get("flutter_app") for lib in native_libs)
    
    if is_flutter:
        # Flutter: skip R2 static analysis (Dart AOT is unreadable by R2)
        # Go straight to ADB recon + AI dynamic analysis
        print(f"[FLUTTER] Skipping R2 analysis — Dart AOT binary not analyzable by R2")
        native_prompt = f"""## Flutter App Detected
**Package:** {package_name}
**Architecture:** Dart AOT compiled to native (`libapp.so`)
**Static analysis:** SKIPPED — Dart AOT binary requires specialized tools (blutter/darter), R2 cannot analyze it.
**Approach:** Use Dynamic Analysis — hook `javax.crypto.Cipher.doFinal` to intercept FlutterSecureStorage encrypt/decrypt operations.
"""
        # ADB Recon: discover app data files
        if package_name:
            print(f"[ADB RECON] Scanning app data directory...")
            adb_recon = native_analyzer.adb_recon_app_data(package_name)
            if adb_recon:
                native_prompt += f"\n## ADB RECON — App Data Directory\n```\n{adb_recon}\n```\n"
                native_prompt += "\n**IMPORTANT:** If you see FlutterSecureStorage.xml above, the app stores encrypted data. Hook Cipher.doFinal to see decrypted values, then spoof them!\n"
                print(f"[ADB RECON] Added {len(adb_recon)} chars of app data context")
    else:
        # Non-Flutter: run full R2 analysis pipeline
        print(f"[NATIVE] Starting deep analysis for {apk_base}...")
        native_prompt = native_analyzer.run_full_analysis(
            apk_folder=apk_base,
            native_libs=native_libs,
            java_context=main_class_code
        )
    
    # Generate script from tested templates (not AI-generated)
    print(f"[NATIVE] Generating template-based script...")
    template_script = native_analyzer.generate_native_script(
        apk_folder=apk_base,
        native_libs=native_libs
    )
    
    # Send to AI for analysis/explanation only
    result = ai_engine.analyze_native_and_generate_hooks(
        package_name=package_name,
        manifest_xml=manifest_xml,
        main_class_code=main_class_code,
        native_analysis=native_prompt
    )
    
    # Template handles strcmp reading (proven pattern)
    # AI handles bypass mode (can analyze code for correct return value)
    if template_script and template_script.strip():
        final_script = template_script
        print("[NATIVE] Using template script (strcmp reading mode)")
    else:
        final_script = result.get("script", "")
        print("[NATIVE] Using AI-generated script (bypass mode)")
    
    # Save analysis context for refine_script to use later
    app_state.last_analysis_context = {
        "native_prompt": native_prompt[:5000],
        "java_code": main_class_code[:5000],
        "manifest_xml": manifest_xml[:3000],
        "package_name": package_name,
        "apk_name": apk_base,
    }
    
    return {
        "script": final_script,
        "analysis": result.get("analysis", ""),
        "package": package_name,
        "main_activity": main_activity,
        "success": bool(final_script)
    }



@router.post("/heal-script")
async def ai_heal_script(data: HealScriptRequest):
    """
    Heals a broken Frida script based on error log.
    Now includes decompiled class context for TypeError fixes.
    """
    try:
        # Extract class names from error and lookup their code
        class_context = ""
        if data.apk_folder:
            class_names = extract_class_names_from_error(data.error + data.script)
            for class_name in class_names[:3]:  # Limit to 3 classes
                code = find_class_in_decompiled(class_name, data.apk_folder)
                if code:
                    class_context += f"\n\n## Real Class: {class_name}\n```java\n{code}\n```"
        
        healed_script = ai_engine.heal_script(
            data.script, 
            data.error, 
            data.history,
            class_context  # Pass class context
        )
        return {
            "healed_script": healed_script,
            "success": True,
            "message": "Script healed successfully",
            "classes_found": len(class_context) > 0
        }
    except Exception as e:
        return {
            "healed_script": data.script,
            "success": False,
            "message": f"Error healing script: {str(e)}"
        }


@router.post("/refine-script")
async def ai_refine_script(data: RefineScriptRequest):
    """
    Refines an existing Frida script based on user feedback.
    This is for when the script is close but needs adjustments.
    """
    try:
        # Get decompiled code context if APK folder provided
        class_context = ""
        if data.apk_folder:
            # Try to get MainActivity and related classes
            main_class = find_class_in_decompiled("MainActivity", data.apk_folder)
            if main_class:
                class_context = f"## MainActivity:\n```java\n{main_class}\n```"
            
            # Also extract any classes mentioned in the current script
            class_names = extract_class_names_from_error(data.script)
            for class_name in class_names[:2]:
                code = find_class_in_decompiled(class_name, data.apk_folder)
                if code and class_name != "MainActivity":
                    class_context += f"\n\n## {class_name}:\n```java\n{code}\n```"
        
        # Get stored analysis context
        analysis_ctx = app_state.last_analysis_context
        analysis_text = analysis_ctx.get("native_prompt", "")
        
        refined_script = ai_engine.refine_script(
            current_script=data.script,
            user_feedback=data.feedback,
            class_context=class_context,
            frida_logs=data.frida_logs,
            analysis_context=analysis_text
        )
        
        return {
            "script": refined_script,
            "success": True,
            "message": "Script refined based on feedback"
        }
    except Exception as e:
        return {
            "script": data.script,
            "success": False,
            "message": f"Error refining script: {str(e)}"
        }


# ============ Report Generation ============

import json
from datetime import datetime
from fastapi import Request
from fastapi.responses import FileResponse


class GenerateReportRequest(BaseModel):
    script: str = ""
    frida_logs: str = ""


@router.post("/generate-report")
async def ai_generate_report(data: GenerateReportRequest):
    """Generate penetration test report with vulnerability scoring. (PROMPT #5)"""
    
    package_name = app_state.last_analysis_context.get("package_name", "unknown")
    
    result = ai_engine.generate_report(
        package_name=package_name,
        script=data.script,
        frida_logs=data.frida_logs,
        analysis_context=app_state.last_analysis_context
    )
    
    if not result.get("success"):
        return result
    
    # Save report to file
    os.makedirs("reports", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_pkg = package_name.replace(".", "_")
    filename = f"{timestamp}_{safe_pkg}"
    
    report_data = result["report"]
    report_data["created_at"] = datetime.now().isoformat()
    report_data["filename"] = filename
    report_data["script_code"] = data.script[:5000]  # Store actual script code
    report_data["apk_name"] = app_state.last_analysis_context.get("apk_name", "")
    
    json_path = f"reports/{filename}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    
    # Generate PDF
    pdf_path = _generate_pdf(report_data, filename)
    
    print(f"[REPORT] Saved: {json_path}")
    if pdf_path:
        print(f"[REPORT] PDF: {pdf_path}")
    
    return {
        "success": True,
        "report": report_data,
        "score": result.get("score", 5),
        "filename": filename,
        "pdf_url": f"/api/reports/download/{filename}" if pdf_path else None
    }


# Reports router (separate prefix)
reports_router = APIRouter(prefix="/api/reports", tags=["reports"])


@reports_router.get("/list")
async def list_reports():
    """List all saved reports."""
    reports_dir = "reports"
    if not os.path.exists(reports_dir):
        return {"reports": []}
    
    reports = []
    for fname in sorted(os.listdir(reports_dir), reverse=True):
        if not fname.endswith(".json"):
            continue
        
        fpath = os.path.join(reports_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            reports.append({
                "filename": fname.replace(".json", ""),
                "app_name": data.get("app_name", "unknown"),
                "score": data.get("score", 0),
                "summary": data.get("summary", "")[:100],
                "vulnerabilities": data.get("vulnerabilities", []),
                "created_at": data.get("created_at", ""),
                "pdf_available": os.path.exists(fpath.replace(".json", ".pdf"))
            })
        except Exception as e:
            print(f"[REPORT] Error reading {fname}: {e}")
    
    return {"reports": reports}


@reports_router.post("/delete")
async def delete_report(request: Request):
    """Delete a report by filename."""
    data = await request.json()
    filename = data.get("filename", "")
    
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return {"success": False, "error": "Invalid filename"}
    
    deleted = False
    for ext in [".json", ".pdf"]:
        fpath = f"reports/{filename}{ext}"
        if os.path.exists(fpath):
            os.remove(fpath)
            deleted = True
            print(f"[REPORT] Deleted: {fpath}")
    
    return {"success": deleted}


@reports_router.get("/download/{filename}")
async def download_report_pdf(filename: str):
    """Download report as PDF."""
    if ".." in filename or "/" in filename or "\\" in filename:
        return {"error": "Invalid filename"}
    
    pdf_path = f"reports/{filename}.pdf"
    if not os.path.exists(pdf_path):
        # Try to regenerate from JSON
        json_path = f"reports/{filename}.json"
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                report_data = json.load(f)
            _generate_pdf(report_data, filename)
        
        if not os.path.exists(pdf_path):
            return {"error": "PDF not found"}
    
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"report_{filename}.pdf"
    )


def _safe_text(text: str) -> str:
    """Remove characters that fpdf can't encode with latin-1 fallback."""
    if not text:
        return ""
    # Replace common problematic characters
    replacements = {
        '\u200b': '',   # Zero-width space
        '\u200c': '',   # Zero-width non-joiner
        '\u200d': '',   # Zero-width joiner
        '\ufeff': '',   # BOM
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _generate_pdf(report_data: dict, filename: str) -> str:
    """Generate PDF from report data using fpdf2 with proper encoding."""
    try:
        from fpdf import FPDF
        
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_margins(left=15, top=15, right=15)
        pdf.add_page()
        
        # Calculate usable width
        W = pdf.w - pdf.l_margin - pdf.r_margin
        
        # Try fonts in order: THSarabunNew > DejaVuSans > Helvetica fallback
        font_dir = os.path.join(os.path.dirname(__file__), "..", "fonts")
        font_name = "Helvetica"
        use_unicode = False
        
        th_font = os.path.join(font_dir, "THSarabunNew.ttf")
        th_font_bold = os.path.join(font_dir, "THSarabunNew Bold.ttf")
        deja_font = os.path.join(font_dir, "DejaVuSans.ttf")
        deja_font_bold = os.path.join(font_dir, "DejaVuSans-Bold.ttf")
        
        if os.path.exists(th_font):
            pdf.add_font("THSarabun", "", th_font, uni=True)
            bold_path = th_font_bold if os.path.exists(th_font_bold) else th_font
            pdf.add_font("THSarabun", "B", bold_path, uni=True)
            font_name = "THSarabun"
            use_unicode = True
            print("[REPORT] Using THSarabunNew font (Thai support)")
        elif os.path.exists(deja_font):
            pdf.add_font("DejaVu", "", deja_font, uni=True)
            bold_path = deja_font_bold if os.path.exists(deja_font_bold) else deja_font
            pdf.add_font("DejaVu", "B", bold_path, uni=True)
            font_name = "DejaVu"
            use_unicode = True
            print("[REPORT] Using DejaVuSans font (Unicode support)")
        else:
            print(f"[REPORT] No Unicode font found in {font_dir}, using Helvetica (ASCII only)")
        
        def safe(text):
            if use_unicode:
                return _safe_text(str(text))
            return ''.join(c if ord(c) < 128 else '?' for c in str(text))
        
        def write_multi(text, h=6):
            """Safe multi_cell that resets position and uses explicit width."""
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(w=W, h=h, text=safe(text), align="L")
        
        def write_cell(text, h=10, bold=False, size=10, align="L", color=None):
            """Safe cell that resets position."""
            if color:
                pdf.set_text_color(*color)
            if bold:
                pdf.set_font(font_name, "B", size)
            else:
                pdf.set_font(font_name, "", size)
            pdf.set_x(pdf.l_margin)
            pdf.cell(w=W, h=h, text=safe(text), ln=True, align=align)
            if color:
                pdf.set_text_color(0, 0, 0)
        
        # ===== Title =====
        write_cell("Penetration Test Report", h=16, bold=True, size=28, align="C")
        write_cell(f"Generated: {report_data.get('created_at', '')[:19]}", h=10, size=16, align="C")
        pdf.ln(5)
        
        # ===== App Name =====
        apk_display = report_data.get('apk_name', '')
        pkg_display = report_data.get('app_name', 'unknown')
        if apk_display:
            write_cell(f"APK: {apk_display}", h=12, bold=True, size=20)
            write_cell(f"Package: {pkg_display}", h=10, bold=False, size=16)
        else:
            write_cell(f"App: {pkg_display}", h=12, bold=True, size=20)
        pdf.ln(2)
        
        # ===== Score =====
        score = report_data.get("score", 0)
        score_color = (220, 50, 50) if score >= 7 else (230, 150, 0) if score >= 4 else (50, 180, 50)
        write_cell(f"Vulnerability Score: {score}/10", h=18, bold=True, size=30, align="C", color=score_color)
        
        score_reason = report_data.get("score_reason", "")
        if score_reason:
            pdf.set_font(font_name, "", 16)
            write_multi(score_reason)
        pdf.ln(5)
        
        # ===== Separator =====
        pdf.set_draw_color(200, 200, 200)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(5)
        
        # ===== Test Steps =====
        write_cell("Test Steps", bold=True, size=22)
        pdf.set_font(font_name, "", 16)
        for i, step in enumerate(report_data.get("test_steps", []), 1):
            write_multi(f"{i}. {step}")
        pdf.ln(3)
        
        # ===== Vulnerabilities =====
        write_cell("Vulnerabilities Found", bold=True, size=22, color=(200, 50, 50))
        pdf.set_font(font_name, "", 16)
        for vuln in report_data.get("vulnerabilities", []):
            write_multi(f"- {vuln}")
        pdf.ln(3)
        
        # ===== Script Description =====
        write_cell("Script Description", bold=True, size=22)
        pdf.set_font(font_name, "", 16)
        write_multi(report_data.get("script_used", ""))
        pdf.ln(3)
        
        # ===== Script Code =====
        script_code = report_data.get("script_code", "")
        if script_code:
            write_cell("Script Code", bold=True, size=22)
            pdf.set_font("Courier", "", 9)
            pdf.set_fill_color(240, 240, 240)
            lines = script_code.split('\n')[:50]
            for line in lines:
                display_line = line[:100] if len(line) > 100 else line
                try:
                    pdf.set_x(pdf.l_margin)
                    pdf.cell(w=W, h=4, text=display_line, ln=True, fill=True)
                except:
                    ascii_line = display_line.encode('ascii', errors='replace').decode('ascii')
                    pdf.set_x(pdf.l_margin)
                    pdf.cell(w=W, h=4, text=ascii_line, ln=True, fill=True)
            if len(script_code.split('\n')) > 50:
                pdf.set_x(pdf.l_margin)
                pdf.cell(w=W, h=4, text="... (truncated)", ln=True, fill=True)
            pdf.set_fill_color(255, 255, 255)
            pdf.ln(3)
        
        # ===== Summary =====
        write_cell("Summary", bold=True, size=22)
        pdf.set_font(font_name, "", 16)
        write_multi(report_data.get("summary", ""))
        pdf.ln(3)
        
        # ===== Remediation =====
        write_cell("Remediation", bold=True, size=22, color=(0, 120, 0))
        pdf.set_font(font_name, "", 16)
        for i, rem in enumerate(report_data.get("remediation", []), 1):
            write_multi(f"{i}. {rem}")
        
        # ===== Save =====
        pdf_path = f"reports/{filename}.pdf"
        pdf.output(pdf_path)
        print(f"[REPORT] PDF generated: {pdf_path}")
        return pdf_path
        
    except Exception as e:
        import traceback
        print(f"[REPORT] PDF generation failed: {e}")
        traceback.print_exc()
        return None


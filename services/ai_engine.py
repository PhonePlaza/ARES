"""
AIEngine - AI-powered Frida script generation, healing, and refinement.
Supports Groq (Llama) and Anthropic (Claude) providers.
"""

import os
import re
from groq import Groq
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()



FRIDA_CHEAT_SHEET = """
## RULES (CRITICAL!)

### 1. SIMPLICITY FIRST - DO THE ABSOLUTE MINIMUM!
- If calling ONE method with the right argument solves it → DO ONLY THAT
- If setting ONE static variable solves it → DO ONLY THAT
- If hooking ONE method solves it → DO ONLY THAT
- **DO NOT** add crypto hooks, button clicks, Java.choose unless specifically needed
- CTF challenges usually need 10-20 lines, NOT 50+ lines
- **METHOD NAMES MUST BE EXACT** — copy from source code, DO NOT rename to camelCase!
  - Source says `get_flag` → use `get_flag`, NOT `getFlag`
  - Source says `check_password` → use `check_password`, NOT `checkPassword`

### 2. Common Patterns (pick ONE that fits — try in this order):

**Pattern A - Call Method on New Instance (for CTF: "get flag", "decrypt", etc.):**
```javascript
Java.perform(function() {
    var ClassName = Java.use("com.example.ClassName");
    var instance = ClassName.$new();  // Create new instance
    var result = instance.targetMethod(1337);  // Call with correct args
    console.log("[+] Result: " + result);
});
```
USE WHEN: A class has a method that returns something (flag, secret, etc.) and just needs to be called with the right argument.

**Pattern B - Static Variable (for CTF challenges):**
```javascript
Java.perform(function() {
    setTimeout(function() {
        var ClassName = Java.use("com.example.ClassName");
        ClassName.fieldName.value = correctValue;  // .value REQUIRED!
        console.log("[+] Value set!");
    }, 500);  // Wait for app to initialize
});
```
USE WHEN: Need to change a static field value. setTimeout is needed because script runs before app is fully loaded.

**Pattern C - Method Hook (no setTimeout needed - hooks wait for call):**
```javascript
Java.perform(function() {
    var ClassName = Java.use("com.example.ClassName");
    ClassName.checkMethod.implementation = function() {
        return true;  // or false, depending on what bypasses
    };
});
```
USE WHEN: Need to change what a method returns (bypass checks, force true/false, etc.)

**Pattern D - Crypto Spy (Monitor Encryption/Decryption):**
```javascript
Java.perform(function() {
    var Cipher = Java.use("javax.crypto.Cipher");
    var Str = Java.use("java.lang.String");
    Cipher.doFinal.overload("[B").implementation = function(input) {
        var algor = this.getAlgorithm();
        var inputStr = Str.$new(input, "UTF-8").toString();
        var result = this.doFinal(input);
        var outputStr = Str.$new(result, "UTF-8").toString();
        console.log("[CRYPTO " + algor + "] Input: " + inputStr + " → Output: " + outputStr);
        return result;
    };
});
```
USE WHEN: You need to monitor all Java-based encryption/decryption operations (AES, RSA, etc.) to find hidden strings or payloads.

### 3. NEVER DO THESE (unless user explicitly asks):
-  `Java.enumerateLoadedClasses()` — NEVER use for simple tasks
-  `getDeclaredMethods()` — NEVER use just to list methods
-  `setTimeout()` with `Java.choose()` — usually unnecessary
-  Adding "exploration" code (listing classes/methods) when the source code is already provided
-  Java.choose() when you can just use $new()
-  Java.scheduleOnMainThread() unless doing UI operations
-  Wrapping everything in try-catch with generic error handling

### 4. AVOID These (unless absolutely necessary):
- Java.choose (only if need existing instance that holds state)
- Crypto hooks (only if need to dump keys)
- Auto-clicking buttons programmatically

### 5. You can combine multiple patterns in one script if needed

### 6. **ALWAYS generate a script** — NEVER respond with only analysis and no code

"""


class AIEngine:
    """AI engine for Frida script generation, healing, and refinement."""
    
    def __init__(self):
        """Initialize AI provider from .env (claude or groq)."""
        self.provider = os.getenv("AI_PROVIDER", "groq").lower()
        
        if self.provider == "claude":
            self.claude_api_key = os.getenv("CLAUDE_API")
            
            if not self.claude_api_key:
                print("[WARNING] CLAUDE_API not found in .env, falling back to Groq")
                self.provider = "groq"
            else:
                self.client = Anthropic(api_key=self.claude_api_key)
                self.model = "claude-opus-4-6"
                print(f"[AI] Using Claude Opus 4.6")
        
        if self.provider == "groq":
            self.groq_api_key = os.getenv("GROQ_API_KEY")
            
            if not self.groq_api_key:
                print("[WARNING] GROQ_API_KEY not found in .env")
            
            self.client = Groq(api_key=self.groq_api_key)
            self.model = "llama-3.3-70b-versatile"
            print(f"[AI] Using Groq Llama 3.3 70B")
    
    

    
    def _call_ai(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        """Unified AI call supporting both Claude and Groq providers."""
        try:
            if self.provider == "claude":
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}]
                )
                return response.content[0].text
            
            else:
                completion = self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    model=self.model,
                    temperature=temperature,
                )
                return completion.choices[0].message.content
                
        except Exception as e:
            print(f"[AI ERROR] {str(e)}")
            raise RuntimeError(f"AI call failed: {str(e)}") from e
    
    


    def heal_script(self, broken_script: str, error_log: str, 
                    healing_history: list = None, class_context: str = "") -> str:
        """Fix a broken Frida script based on its runtime error log."""
        class_hint = ""
        if class_context:
            class_hint = f"\nREAL CLASS INFO:\n{class_context[:2000]}\n"
        
        prompt = f"""Fix this Frida script error. Make the SMALLEST possible change.

ERROR:
{error_log[:2000]}
{class_hint}
BROKEN SCRIPT:
{broken_script}

RULES:
1. FIX ONLY the specific error - do NOT rewrite the whole script
2. NEVER use waitForJava() or polling wrappers
3. NEVER nest Java.perform inside Java.perform
4. Static variable: ClassName.varName.value = X
5. Overload: .overload('android.view.View')
6. Return ONLY the fixed JavaScript code, nothing else
7. **METHOD NAME FIX**: If error says "TypeError: not a function", look at the error log for the REAL method name.
   - Example: if error log shows `Check.get_flag(int)` but script uses `getFlag` → change to `get_flag`
   - Method names MUST be EXACT - do NOT convert to camelCase!
8. If the error log shows method signatures like `public java.lang.String ClassName.methodName(type)`,
   use that EXACT method name in the fix
9. Remove unnecessary code: enumerateLoadedClasses, getDeclaredMethods, setTimeout — keep ONLY what's needed

GOOD EXAMPLE:
Java.perform(() => {{
    var Checker = Java.use("com.example.Checker");
    Checker.code.value = 512;
}});
"""
        
        try:
            raw_content = self._call_ai(
                system_prompt="Return ONLY JavaScript code. No markdown. No explanations. Start with Java.perform",
                user_prompt=prompt,
                temperature=0.1
            )
        except RuntimeError as e:
            print(f"[AI ERROR] Healing failed: {e}")
            return broken_script
        

        print(f"[AI RAW] First 200 chars: {repr(raw_content[:200])}")
        
        cleaned = self._clean_script_response(raw_content)
        print(f"[AI CLEANED] First 200 chars: {repr(cleaned[:200])}")
        
        cleaned = self._strip_wrapper(cleaned)
        
        if not self._is_valid_js_start(cleaned):
            print(f"[AI ERROR] Invalid JS - returning original script")
            return broken_script
        
        return cleaned
    
    
    def refine_script(self, current_script: str, user_feedback: str, 
                      class_context: str = "", frida_logs: str = "",
                      analysis_context: str = "") -> str:
        """Refine an existing Frida script based on user feedback."""
        class_section = ""
        if class_context:
            class_section = f"\n## DECOMPILED JAVA CODE:\n{class_context[:3000]}\n"
        
        log_section = ""
        if frida_logs:
            log_section = f"\n## FRIDA LOG OUTPUT:\n{frida_logs[:500]}\n"
        
        analysis_section = ""
        if analysis_context:
            analysis_section = f"\n## PREVIOUS ANALYSIS CONTEXT:\n{analysis_context[:3000]}\n"

        prompt = f"""Fix this Frida script. The current version is not working correctly.

{FRIDA_CHEAT_SHEET}

## CURRENT SCRIPT:
```javascript
{current_script}
```
{class_section}{log_section}{analysis_section}
## USER FEEDBACK: {user_feedback}

## RULES:
1. Use patterns from the FRIDA QUICK REFERENCE above
2. If method affects UI → wrap in Java.scheduleOnMainThread
3. DO NOT use Java.scheduleOnMainThread for non-UI methods
4. Return ONLY the fixed JavaScript code, nothing else"""

        try:
            raw_content = self._call_ai(
                system_prompt="You fix Frida scripts. Return ONLY JavaScript code. No markdown. No explanations.",
                user_prompt=prompt,
                temperature=0.1
            )
        except RuntimeError as e:
            print(f"[AI ERROR] Refine failed: {e}")
            return current_script
        
        cleaned = self._clean_script_response(raw_content)
        print(f"[AI CLEANED] First 100: {repr(cleaned[:100])}")
        
        cleaned = self._strip_wrapper(cleaned)
        
        # Validate
        if not self._is_valid_js_start(cleaned):
            print(f"[AI ERROR] Invalid refined script - returning original")
            print(f"[AI DEBUG] Cleaned content was: {repr(cleaned[:200])}")
            return current_script
        
        return cleaned
    
    def generate_report(self, package_name: str, script: str, 
                        frida_logs: str = "", analysis_context: dict = None) -> dict:
        """Generate penetration test report with vulnerability scoring. (PROMPT #5)"""
        
        context_info = ""
        if analysis_context:
            if analysis_context.get("manifest_xml"):
                context_info += f"\n**Manifest:**\n{analysis_context['manifest_xml'][:2000]}"
            if analysis_context.get("java_code"):
                context_info += f"\n**Java Code:**\n{analysis_context['java_code'][:3000]}"
            if analysis_context.get("native_prompt"):
                context_info += f"\n**Native Analysis:**\n{analysis_context['native_prompt'][:2000]}"
        
        prompt = f"""คุณเป็นผู้เชี่ยวชาญ Mobile Security ช่วยเขียนรายงานผลการทดสอบเจาะระบบ (Penetration Test Report)

## ข้อมูลแอป
**Package:** {package_name}
{context_info}

## Script ที่ใช้ทดสอบ
```javascript
{script[:4000]}
```

## ผลลัพธ์จาก Frida Log
```
{frida_logs[:3000] if frida_logs else "(ไม่มี log)"}
```

---

## คำสั่ง: เขียนรายงานเป็นภาษาไทย ตามโครงสร้างนี้

ตอบเป็น JSON format เท่านั้น:
```json
{{
  "app_name": "ชื่อแอป (package name)",
  "test_steps": [
    "ขั้นตอนที่ 1: ...",
    "ขั้นตอนที่ 2: ...",
    "ขั้นตอนที่ 3: ..."
  ],
  "vulnerabilities": [
    "ช่องโหว่ที่ 1: ...",
    "ช่องโหว่ที่ 2: ..."
  ],
  "script_used": "สรุปสั้นๆ ว่า script ทำอะไร",
  "score": 7,
  "score_reason": "เหตุผลที่ให้คะแนนนี้",
  "summary": "สรุปผลการทดสอบโดยรวม",
  "remediation": [
    "วิธีป้องกันที่ 1: ...",
    "วิธีป้องกันที่ 2: ..."
  ]
}}
```

## เกณฑ์ให้คะแนน (score 1-10):
- 1-3: ช่องโหว่เล็กน้อย (info leak, debug flag)
- 4-6: ช่องโหว่ปานกลาง (hardcoded secret, weak crypto)
- 7-8: ช่องโหว่รุนแรง (bypass authentication, root detection bypass)
- 9-10: ช่องโหว่วิกฤต (RCE, data theft, full bypass)

## Rules:
1. ตอบเป็น JSON เท่านั้น ห้ามมี text อื่นนอก JSON
2. เขียนเป็นภาษาไทย
3. วิเคราะห์จาก script + log + source code ที่ให้
4. ถ้าไม่มี log ให้วิเคราะห์จาก script + source code
"""
        
        try:
            raw_content = self._call_ai(
                system_prompt="You are a mobile security expert writing penetration test reports. Return ONLY valid JSON. No markdown fences. No extra text.",
                user_prompt=prompt,
                temperature=0.2
            )
            
            # Clean JSON from response
            content = raw_content.strip()
            if "<think>" in content:
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            content = content.strip()
            
            import json
            report_data = json.loads(content)
            
            return {
                "success": True,
                "report": report_data,
                "score": report_data.get("score", 5)
            }
            
        except json.JSONDecodeError as e:
            print(f"[AI ERROR] Report JSON parse failed: {e}")
            print(f"[AI DEBUG] Raw content: {raw_content[:500]}")
            return {
                "success": False,
                "error": f"AI response was not valid JSON: {str(e)}"
            }
        except RuntimeError as e:
            print(f"[AI ERROR] Report generation failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _clean_script_response(self, content: str) -> str:
        """Extract JavaScript code from AI response, removing markdown/think tags/prefixes."""
        if not content:
            return ""
        
        if "<think>" in content:
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
            print(f"[AI] Stripped <think> tags")
        
        if "</think>" in content:
            content = content.split("</think>")[-1]
            print(f"[AI] Stripped content before </think>")
        
        if "```javascript" in content:
            content = content.split("```javascript")[1].split("```")[0]
        elif "```js" in content:
            content = content.split("```js")[1].split("```")[0]
        elif "```" in content:
            parts = content.split("```")
            if len(parts) >= 2:
                content = parts[1]
                if content.startswith("javascript") or content.startswith("js"):
                    content = content.split("\n", 1)[1] if "\n" in content else ""
        
        prefixes_to_remove = [
            "Here's the fixed script:",
            "Here is the fixed script:",
            "Fixed script:",
            "The fixed script:",
            "Here's the corrected code:",
            "Corrected code:",
        ]
        for prefix in prefixes_to_remove:
            if content.strip().startswith(prefix):
                content = content.strip()[len(prefix):]
        
        reasoning_patterns = [
            "\n\nWait,", "\nWait,",
            "\n\nBut ", "\nBut ",
            "\n\nSo,", "\nSo,", 
            "\n\nHowever,", "\nHowever,",
            "\n\nNote:", "\nNote:",
            "\n\nThis script ", "\nThis script ",
            "\n\nThe above", "\nThe above",
            "\n\nLet me", "\nLet me",
            "\n\nI need", "\nI need",
            "\n\nI have", "\nI have",
            "\n\nAlternative", "\nAlternative",
            "\n\nAnother", "\nAnother",
        ]
        for pattern in reasoning_patterns:
            if pattern in content:
                content = content.split(pattern)[0]
                print(f"[AI] Stripped reasoning text at pattern: {pattern.strip()[:20]}")
        
        return content.strip()
    
    def _is_valid_js_start(self, code: str) -> bool:
        """Check if code begins with a valid JavaScript pattern."""
        if not code:
            return False
        
        valid_starts = [
            "Java.perform", "Java.schedule", "Java.use",
            "function", "var ", "let ", "const ",
            "//", "/*", "(function", "setImmediate",
            "setTimeout", "console.log", "'use strict'",
            "Interceptor", "Module.", "Process.",  # Native hooks
        ]
        
        code_trimmed = code.strip()
        for start in valid_starts:
            if code_trimmed.startswith(start):
                return True
        
        return False
    
    def _strip_wrapper(self, code: str) -> str:
        """Remove unnecessary wrappers (waitForJava, nested Java.perform) from code.
        IMPORTANT: Do NOT strip code before Java.perform — native hooks belong there.
        """
        # Only strip waitForJava wrappers — extract the inner Java.perform block
        if "waitForJava" in code or "function waitFor" in code:
            match = re.search(r'Java\.perform\s*\(\s*function\s*\(\s*\)', code)
            if match:
                start_idx = match.start()
                
                brace_count = 0
                end_idx = start_idx
                in_string = False
                string_char = None
                prev_char = None
                for i, char in enumerate(code[start_idx:], start_idx):
                    if char in '"\'`' and not in_string:
                        in_string = True
                        string_char = char
                    elif char == string_char and in_string and prev_char != '\\':
                        in_string = False
                    elif not in_string:
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i + 1
                                break
                    prev_char = char
                
                if end_idx > start_idx:
                    # Preserve any code BEFORE Java.perform (native hooks)
                    pre_code = code[:start_idx].strip()
                    extracted = code[start_idx:end_idx]
                    if not extracted.rstrip().endswith(');'):
                        extracted += ');'
                    if pre_code:
                        result = pre_code + "\n\n" + extracted
                    else:
                        result = extracted
                    print(f"[AI] Stripped waitForJava wrapper")
                    return result
        
        # Do NOT strip code before Java.perform — native hooks belong there!
        return code
    
    def _validate_and_clean_script(self, script: str) -> str:
        """Post-processing: remove anti-patterns AI tends to generate despite instructions."""
        if not script or not script.strip():
            return script
        
        original = script
        
        script = re.sub(
            r'Java\.enumerateLoadedClasses\s*\(\s*\{[\s\S]*?\}\s*\)\s*;',
            '',
            script
        )
        
        script = re.sub(
            r'var\s+methods\s*=.*?getDeclaredMethods[\s\S]*?\}\s*\n',
            '',
            script
        )
        
        script = re.sub(
            r'(?:var\s+\w+\s*=\s*)?Java\.enumerateLoadedClassesSync\s*\([\s\S]*?\)[\s\S]*?;',
            '',
            script
        )
        
        cleaned = re.sub(r'\s+', '', script)
        if 'Java.perform' in script and len(cleaned) < 30:
            print(f"[AI-VALIDATE] Script was only enumeration code, returning empty")
            return "// AI generated only exploration code. Please provide more specific goal."
        
        if script != original:
            print(f"[AI-VALIDATE] Stripped anti-patterns from generated script")
        
        return script.strip()
    
    

    
    def analyze_and_generate_hooks(self, package_name: str, manifest_xml: str, 
                                    main_class_code: str, additional_classes: list = None) -> dict:
        """Analyze APK source code and generate Frida hooks automatically."""
        additional_context = ""
        if additional_classes:
            for i, cls in enumerate(additional_classes[:3]):
                additional_context += f"\n\n--- Additional Class {i+1} ---\n{cls[:3000]}"
        
        prompt = f"""You are an Android security expert. Generate the **SIMPLEST** working Frida script.

## TARGET APP

**Package:** {package_name}

**Manifest:**
```xml
{manifest_xml[:5000]}
```

**Source Code:**
```java
{main_class_code[:8000]}
```
{additional_context}
{FRIDA_CHEAT_SHEET}

---

## OUTPUT FORMAT
1. **การวิเคราะห์**:
   - ช่องโหว่ที่พบ (list ทุกจุด)
   - เป้าหมาย: method/class ที่ต้อง hook หรือเรียก
   - Pattern ที่เลือก (A/B/C) และเหตุผล
2. **Frida Script** (สั้นที่สุด, ไม่เกิน 40 บรรทัด เกินได้ถ้าจำเป็น)
"""
        
        try:
            response = self._call_ai(
                system_prompt="You are a mobile security expert. Generate CORRECT and CLEAN Frida scripts. Avoid unnecessary complexity but include all required code.",
                user_prompt=prompt,
                temperature=0.2
            )
        except RuntimeError as e:
            return {
                "script": "",
                "analysis": f"AI Error: {str(e)}",
                "package": package_name,
                "success": False
            }
        
        script = ""
        analysis = ""
        
        if "```javascript" in response:
            parts = response.split("```javascript")
            analysis = parts[0].strip()
            script = parts[1].split("```")[0].strip()
        elif "```js" in response:
            parts = response.split("```js")
            analysis = parts[0].strip()
            script = parts[1].split("```")[0].strip()
        elif "```" in response:
            parts = response.split("```")
            analysis = parts[0].strip()
            raw_code = parts[1] if len(parts) > 1 else ""
            if raw_code.startswith(("javascript", "js")):
                raw_code = raw_code.split("\n", 1)[1] if "\n" in raw_code else ""
            script = raw_code.split("```")[0].strip()
        else:
            script = response
            analysis = "Analysis included in script comments."
        
        if script:
            script = self._strip_wrapper(script)
            script = self._validate_and_clean_script(script)
            script = script.strip()
        
        has_script = bool(script and script.strip())
        
        return {
            "script": script if has_script else "",
            "analysis": analysis,
            "package": package_name,
            "success": has_script
        }
    
    

    
    def analyze_native_and_generate_hooks(self, package_name: str, manifest_xml: str,
                                           main_class_code: str, native_analysis: str) -> dict:
        """Analyze native .so files with Java context and generate Frida hooks."""
        prompt = f"""You are an expert in Reverse Engineering and Penetration Testing on Android.

{FRIDA_CHEAT_SHEET}

## TARGET APP

**Package:** {package_name}

**Manifest (excerpt):**
```xml
{manifest_xml[:3000]}
```

**Decompiled Java Source Code:**
```java
{main_class_code[:5000]}
```

---

{native_analysis}

---

## YOUR TASK — THINK STEP BY STEP!

**You MUST analyze the code BEFORE writing any script.** Do NOT just pattern-match from examples.

### STEP 1: SCAN FOR PROTECTIONS (read the Java code carefully!)
Look for these patterns IN THE ACTUAL CODE provided above:
- `System.exit` or `Runtime.exit` → app kills itself (need to block)
- `ptrace`, `fork`, `waitpid` in native imports → anti-debug (need to hook ALL from libc)
- Classes with root/integrity checks (methods returning boolean) → bypass with `return false`
- Alert dialogs that call `finish()` or `exit()` → block the dialog trigger method
- **List every protection you find** — missing even one will crash the script
- **Flutter apps:** If you see `libflutter.so` — this is a Flutter app! Skip libflutter.so (it's the framework engine). Focus on `libapp.so` which contains the developer's Dart code compiled AOT to native. Standard JNI patterns may not apply to Flutter apps.

### STEP 2: IDENTIFY THE CORE CHALLENGE (what does the native function actually do?)
- What comparison function is used? (strcmp, strncmp, memcmp, custom?)
- What is the check function's return type? (int, boolean, jstring?)
- What value means "success"? (1, 0, 1337, specific constant?) — **READ THE JAVA CODE to find this!**
- Is user input compared against a secret? Or is a hash/encryption involved?

### STEP 3: CHOOSE YOUR STRATEGY
Based on YOUR analysis above, pick the right approach:
- Need to **read a secret** → hook strcmp/strncmp with known input pattern
- Need to **bypass a check** → hook JNI export and replace return value (use correct value from Step 2!)
- App has **protections** → bypass ALL of them first before any other hook

### STEP 4: WRITE THE SCRIPT
Now write the Frida script based on your analysis. Keep it **minimal** (under 40 lines).

## RULES (CRITICAL — READ CAREFULLY!)

###  ANTI-PATTERNS (will cause TypeError/crash, NEVER use these):
```javascript
// WRONG 1: .implementation on native method → TypeError
cls.nativeMethod.implementation = function() {{ ... }};

// WRONG 2: getStringUtfChars is not a Frida API → TypeError
Java.vm.getEnv().getStringUtfChars(args[2], null);

// WRONG 3: retval.replace without ptr() → TypeError
retval.replace(1);  // MUST be retval.replace(ptr(1))

// WRONG 4: Process.findModuleByName outside Java.perform/setTimeout → null/CRASH
// In spawn mode, script runs BEFORE System.loadLibrary
Process.findModuleByName("lib.so");  // null — library not loaded yet

// WRONG 5: Unfiltered Interceptor.attach on strcmp → too much noise
// strcmp is called thousands of times internally
// ALWAYS filter by user input to avoid flooding the console
Interceptor.attach(strcmpAddr, {{ onEnter: function(args) {{
    console.log(args[0].readCString());  // NOISE: logs EVERYTHING
}} }});
```

### TIMING:
Frida runs the script BEFORE `System.loadLibrary` in spawn mode.
**ALWAYS wrap ALL native code inside `Java.perform(() => {{ ... }})`.**

### STRATEGY 1 — Hook JNI export for BYPASS:
Use this to bypass native checks by changing the return value.
Use `Process.findModuleByName` + `getExportByName` (Frida 17+ instance methods).
**IMPORTANT: Analyze the source code to determine the correct bypass value!**
Do NOT always use ptr(1) — look at what value the function checks against (e.g. 1337, 0, specific constants).
```javascript
Java.perform(() => {{
    var lib = Process.findModuleByName("libexample.so");
    if (!lib) {{ console.log("[-] Module not loaded"); return; }}
    console.log("[+] Module base: " + lib.base);
    var addr = lib.getExportByName(
        "Java_com_package_ClassName_methodName");
    console.log("[+] Found @ " + addr);
    Interceptor.attach(addr, {{
        onEnter: function(args) {{
            console.log("[*] Function called");
        }},
        onLeave: function(retval) {{
            console.log("[*] Original return: " + retval.toInt32());
            retval.replace(ptr(CORRECT_VALUE));  // Analyze code for correct value!
            console.log("[+] Replaced return value");
        }}
    }});
}});
```

### STRATEGY 2 — Interceptor.attach strcmp for READING values (when strcmp is used):
Use this to see what values are being compared (reveals passwords/flags).
Hook `strcmp` from `libc.so` via `Interceptor.attach` + **filter by user input** to avoid noise.
Also hook the Java method to capture what the user typed.
```javascript
Java.perform(() => {{
    var strcmpAddr = Process.findModuleByName("libc.so")
                            .getExportByName("strcmp");
    console.log("[+] Found strcmp @ " + strcmpAddr);

    var myInput = "";

    // Hook Java side to capture user input
    var MainActivity = Java.use("com.example.ClassName");
    MainActivity.nativeMethod.implementation = function(input) {{
        myInput = input.toString();
        console.log("[*] User input: " + myInput);
        return this.nativeMethod(input);
    }};

    // Attach to strcmp — filter by user input to avoid noise
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
    console.log("[+] Hooked strcmp via Interceptor.attach (filtered)");
}});
```

### STRATEGY 3 — Anti-debug / Root detection / Exit bypass:
Many apps detect root, debugger, or tampering and call `System.exit()`.
You MUST bypass ALL protections BEFORE hooking native functions.
**Native anti-debug hooks go OUTSIDE `Java.perform()`.** Java hooks go INSIDE.
**MUST hook ALL THREE: ptrace, fork, waitpid** — hooking only ptrace is NOT enough!
**Use try-catch for optional Java classes** — if you're not 100% sure a class exists, wrap in try-catch so script doesn't die.
```javascript
// STEP 1: Block ALL anti-debug (MUST use forEach with ALL THREE!)
var libc = Process.findModuleByName("libc.so");
["ptrace", "fork", "waitpid"].forEach(function(name) {{
    Interceptor.attach(libc.getExportByName(name), {{
        onLeave: function(retval) {{ retval.replace(ptr(0)); }}
    }});
    console.log("[+] Hooked: " + name);
}});

// STEP 2: Java-level bypasses
Java.perform(function() {{
    // REQUIRED: Block exit
    Java.use("java.lang.System").exit.implementation = function(code) {{
        console.log("[+] System.exit(" + code + ") blocked");
    }};
    Java.use("java.lang.Runtime").exit.implementation = function(code) {{
        console.log("[+] Runtime.exit(" + code + ") blocked");
    }};

    // OPTIONAL: Root/debug checks (wrap in try-catch — class may not exist!)
    try {{
        var checker = Java.use("sg.vantagepoint.a.b");
        checker.a.implementation = function() {{ return false; }};
        checker.b.implementation = function() {{ return false; }};
        checker.c.implementation = function() {{ return false; }};
    }} catch(e) {{}}
}});
```

### STRATEGY 4 — strncmp/strcmp with known input pattern:
When you can't easily capture user input from Java, use a **known pattern** (e.g. lots of 'A's).
The **exact number of A's** must match the comparison length — find the length from strncmp's 3rd argument or from the source code.
**IMPORTANT: Use `"A".repeat(N)` in console.log instead of typing A's manually** — do NOT try to count A's by hand, you WILL get it wrong.
```javascript
var libc = Process.findModuleByName("libc.so");
var strncmpAddr = libc.getExportByName("strncmp");
Interceptor.attach(strncmpAddr, {{
    onEnter: function(args) {{
        try {{
            var s1 = args[0].readUtf8String();
            if (s1 && s1.startsWith("AAAA")) {{
                console.log("[+] Secret: " + args[1].readUtf8String());
                console.log("[+] Required length: " + args[2].toInt32());
            }}
        }} catch(e) {{}}
    }}
}});
// Use "A".repeat(N) — NEVER type A's manually!
console.log("[*] Type " + "A".repeat(23) + " in the app (" + 23 + " chars)");
```

### STRATEGY 5 — Flutter App (libapp.so / Dart AOT):
Flutter apps compile Dart code to native via AOT into `libapp.so`. There are NO JNI exports.
**Static analysis (R2) CANNOT read Dart AOT** — use Dynamic Analysis instead.
**Do NOT hook libc strcmp/memcmp** — they only catch Android framework noise.
**You MUST still generate a working script** — do NOT say "no hooks available".

**PRIMARY: Hook Cipher.doFinal to spoof FlutterSecureStorage values.**
Flutter apps use `FlutterSecureStorage` → encrypts data via `javax.crypto.Cipher`.
Check the ADB RECON data: if you see `FlutterSecureStorage.xml`, the app stores encrypted values (score, flags, etc.).
Hook `Cipher.doFinal` to **intercept decrypted values and spoof them**.

**ANTI-PATTERNS (NEVER use these):**
- `this.getOpmode()` or `this.getOpMode()` → TypeError in Frida! Just check decrypted text directly.
- `return this.doFinal(spoofed)` inside hooked doFinal → **INFINITE RECURSIVE LOOP → CRASH!** The hook calls doFinal again which triggers the hook again forever. Return raw bytes directly: `return Java.array("byte", [48]);`
- Do NOT spoof to a HIGH number (e.g. "999999999") → the stored value is often a TARGET/THRESHOLD score, spoof to "0" to make the check pass.
- Do NOT use regex — use `.includes()` to match values.

```javascript
Java.perform(function() {{
    var Cipher = Java.use("javax.crypto.Cipher");
    var Str = Java.use("java.lang.String");
    Cipher.doFinal.overload("[B").implementation = function(input) {{
        var result = this.doFinal(input);
        try {{
            var text = Str.$new(result, "UTF-8").toString();
            console.log("[doFinal] " + text);
            // Check if decrypted value looks like a target score/threshold
            // ADAPT the value based on what you see in the logs!
            if (text.includes("100000")) {{
                console.log("[+] Spoofing target to 0");
                return Java.array("byte", [48]); // "0"
            }}
        }} catch(e) {{}}
        return result;
    }};
    console.log("[+] Hooked Cipher.doFinal");
}});
```

**SECONDARY: Memory scan libapp.so** (find embedded flag/secret strings):
```javascript
var libapp = Process.findModuleByName("libapp.so");
if (libapp) {{
    ["flag", "CTF", "secret", "score", "win"].forEach(function(pat) {{
        Memory.scan(libapp.base, libapp.size, pat.split("").map(function(c) {{
            return ("0" + c.charCodeAt(0).toString(16)).slice(-2);
        }}).join(" "), {{
            onMatch: function(addr) {{
                try {{
                    var s = addr.readUtf8String(100);
                    if (s && s.length > 3) console.log("[+] " + pat + " @ " + addr + ": " + s);
                }} catch(e) {{}}
            }},
            onComplete: function() {{}}
        }});
    }});
}}
```

### STRATEGY SELECTION:
1. **ALWAYS wrap Java hooks in `Java.perform(function() {{ ... }})`**
2. **Native hooks (libc, Interceptor) can go OUTSIDE `Java.perform`**
3. For bypassing JNI return value → use **Strategy 1** (getExportByName)
4. For reading strcmp compared values → use **Strategy 2** (strcmp + filter by user input)
5. For apps with protections (System.exit, root detection, anti-debug) → use **Strategy 3** FIRST
6. For strncmp when Java hook is complex → use **Strategy 4** (known input "AAAA..." pattern)
7. **Flutter app (libapp.so, no JNI)** → use **Strategy 5** (memory scan + Cipher.doFinal hook)
8. **Any app with standard Java encryption** → use **Pattern D (Crypto Spy)** from the FRIDA_CHEAT_SHEET
9. **If app has anti-tampering, ALWAYS apply Strategy 3 before anything else**
10. You can combine multiple strategies in one script
11. **ALWAYS generate a script** — NEVER respond with only analysis and no code

### For Java-layer Hooks (NON-native methods only):
- `.implementation` ONLY works on regular Java methods (NOT `native`)

### General Rules:
- **SIMPLEST POSSIBLE SCRIPT** — MINIMAL lines, NO unnecessary code
- **EXACT NAMES** — copy from source code
- `public native ...` → MUST use Interceptor on JNI export, NOT .implementation
- **NO verbose console.log** — max 1 log per hook, no ASCII art banners (========)
- **NO try-catch around every hook** — only use try-catch inside onEnter/onLeave for readCString
- **NO if(addr) checks** — getExportByName will throw if not found, that's fine
- Use `.forEach()` loop to hook multiple libc functions in one line
- Keep the script under 40 lines when possible

## OUTPUT FORMAT
1. **การวิเคราะห์** (ตาม Step 1-3):
   - Protections ที่พบ (list ทุกตัว)
   - Core challenge: function ทำอะไร, ค่า success คืออะไร
   - Strategy ที่เลือกและเหตุผล
2. **Frida Script** (สั้นที่สุด, ไม่เกิน 40 บรรทัด)
"""
        
        try:
            response = self._call_ai(
                system_prompt="You are an expert reverse engineer specializing in Android native code analysis. Generate CORRECT Frida scripts that hook both Java and native layers. Include clear explanations of your analysis.",
                user_prompt=prompt,
                temperature=0.3
            )
        except RuntimeError as e:
            return {
                "script": "",
                "analysis": f"AI Error: {str(e)}",
                "package": package_name,
                "success": False
            }
        
        script = ""
        analysis = ""
        
        if "```javascript" in response:
            parts = response.split("```javascript")
            analysis = parts[0].strip()
            code_and_rest = parts[1].split("```", 1)
            script = code_and_rest[0].strip()
            # Capture analysis text after the code block too
            if len(code_and_rest) > 1 and code_and_rest[1].strip():
                analysis += "\n\n" + code_and_rest[1].strip()
        elif "```js" in response:
            parts = response.split("```js")
            analysis = parts[0].strip()
            code_and_rest = parts[1].split("```", 1)
            script = code_and_rest[0].strip()
            if len(code_and_rest) > 1 and code_and_rest[1].strip():
                analysis += "\n\n" + code_and_rest[1].strip()
        elif "```" in response:
            parts = response.split("```")
            analysis = parts[0].strip()
            raw_code = parts[1] if len(parts) > 1 else ""
            if raw_code.startswith(("javascript", "js")):
                raw_code = raw_code.split("\n", 1)[1] if "\n" in raw_code else ""
            script = raw_code.strip()
            # Capture any text after the code block
            if len(parts) > 2 and parts[2].strip():
                analysis += "\n\n" + parts[2].strip()
        else:
            script = response
            analysis = "Analysis included in script comments."
        
        if script:
            script = self._strip_wrapper(script)
            script = self._validate_and_clean_script(script)
            script = script.strip()
        
        has_script = bool(script and script.strip())
        
        return {
            "script": script if has_script else "",
            "analysis": analysis,
            "package": package_name,
            "success": has_script
        }

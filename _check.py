import py_compile
import sys

files = [
    'main.py',
    'services/agent.py',
    'services/analyzer.py',
    'services/frida_core.py',
    'services/native_analyzer.py',
    'services/ai_engine.py',
    'services/streamer.py',
    'routers/__init__.py',
    'routers/state.py',
    'routers/device.py',
    'routers/streaming.py',
    'routers/apk.py',
    'routers/logcat.py',
    'routers/frida.py',
    'routers/ai.py',
]

errors = []
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f"OK: {f}")
    except py_compile.PyCompileError as e:
        print(f"ERROR: {f} -> {e}")
        errors.append(f)

if errors:
    print(f"\nFAILED: {len(errors)} file(s)")
    sys.exit(1)
else:
    print(f"\nALL {len(files)} FILES PASSED SYNTAX CHECK")

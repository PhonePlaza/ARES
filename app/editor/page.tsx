"use client";

import { useState, useRef, useEffect } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Terminal, Send, Paperclip, Save, Play, Smartphone, Activity, FileText, Sparkles, Square, Loader2, ClipboardList, Download } from "lucide-react";
import { useWebSocket } from "@/components/providers/WebSocketProvider";
import CodeHighlighter from "@/components/ui/CodeHighlighter";

export default function ScriptEditorPage() {
    const { addLog } = useWebSocket();
    const [scriptContent, setScriptContent] = useState("// Frida Script will appear here...\nconsole.log('Hello from Frida-Agent');");
    const [logs, setLogs] = useState<string[]>(["[SYSTEM] Editor Ready.", "[HINT] Type your goal below and click Generate to create a Frida script."]);
    const [input, setInput] = useState("");
    const [isConnected, setIsConnected] = useState(true);

    // Target package for Frida
    const [targetPackage, setTargetPackage] = useState("");
    const [isRunning, setIsRunning] = useState(false);
    const [isGenerating, setIsGenerating] = useState(false);
    const [currentApkFolder, setCurrentApkFolder] = useState(""); // Track APK folder for context-aware healing

    // Report State
    const [isGeneratingReport, setIsGeneratingReport] = useState(false);

    // Frida WebSocket ref
    const fridaWsRef = useRef<WebSocket | null>(null);

    // Frida CLI State
    const [fridaLogs, setFridaLogs] = useState<string[]>([]);
    const fridaLogScrollRef = useRef<HTMLPreElement>(null);
    const [fridaInput, setFridaInput] = useState("");

    // Self-Healing State
    const [isHealing, setIsHealing] = useState(false);
    const [healingMessage, setHealingMessage] = useState("");
    const healingTriggeredRef = useRef(false); // Prevent multiple healing attempts
    const scriptContentRef = useRef(scriptContent); // Track current script for async callbacks
    const healingHistoryRef = useRef<Array<{ error: string, script: string }>>([]); // Track previous attempts
    const apkFolderRef = useRef(""); // Track APK folder for context lookup

    // Tab State
    const [currentTab, setCurrentTab] = useState("editor");

    // Logcat State
    const [logcatLogs, setLogcatLogs] = useState<string[]>([]);
    const logcatWsRef = useRef<WebSocket | null>(null);
    const logcatScrollRef = useRef<HTMLDivElement>(null);
    // Buffer for batching updates
    const logBufferRef = useRef<string[]>([]);

    const editorScrollRef = useRef<HTMLDivElement>(null);

    // References for tap/swipe on img
    const imgRef = useRef<HTMLImageElement>(null);

    // ============ HANDLERS ============

    const handleGenerateScript = async () => {
        if (!input.trim()) {
            setLogs(prev => [...prev, "[ERROR] Please enter a goal for script generation."]);
            return;
        }

        setIsGenerating(true);

        // Always use refine-script — it has more context (CHEAT_SHEET + analysis data)
        setLogs(prev => [...prev, `> ${input}`, "[AI] Processing request..."]);

        try {
            // Get recent frida logs for context
            const recentLogs = fridaLogs.slice(-10).join('\n');

            const response = await fetch('http://localhost:8000/api/ai/refine-script', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    script: scriptContent,
                    feedback: input,
                    apk_folder: currentApkFolder,
                    frida_logs: recentLogs
                })
            });

            const data = await response.json();

            if (data.success && data.script) {
                setScriptContent(data.script);
                setLogs(prev => [...prev, "[AI] ✓ Script updated!"]);
            } else {
                setLogs(prev => [...prev, `[AI] Error: ${data.message || 'Unknown error'}`]);
            }
        } catch (error) {
            setLogs(prev => [...prev, `[AI] Network error: ${error}`]);
        }

        setIsGenerating(false);
        setInput("");
    };

    const handleRunScript = async () => {
        if (!targetPackage.trim()) {
            const pkg = prompt("Enter target package name (e.g., com.example.app):");
            if (!pkg) return;
            setTargetPackage(pkg);
        }

        const pkg = targetPackage.trim() || (await new Promise<string>((resolve) => {
            const p = prompt("Enter target package name:");
            resolve(p || "");
        }));

        if (!pkg) return;
        setTargetPackage(pkg);

        setIsRunning(true);

        // Show the command being executed in Frida CLI tab
        const cmd = `frida -U -f ${pkg} -l script.js`;
        setFridaLogs([`$ ${cmd}`, ""]);
        setLogs(prev => [...prev, `[FRIDA] Running: ${cmd}`]);

        // Connect to Frida WebSocket for output
        connectFridaWs();

        try {
            const response = await fetch('http://localhost:8000/api/frida/spawn', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ package: pkg, script: scriptContent })
            });

            const data = await response.json();

            if (data.status === 'running') {
                setLogs(prev => [...prev, `[FRIDA] ✓ Attached to PID ${data.pid}`]);
            } else {
                setLogs(prev => [...prev, `[FRIDA] Error: ${data.message}`]);
                setIsRunning(false);
            }
        } catch (error) {
            setLogs(prev => [...prev, `[FRIDA] Network error: ${error}`]);
            setIsRunning(false);
        }
    };

    const handleStopScript = async () => {
        try {
            await fetch('http://localhost:8000/api/frida/detach', { method: 'POST' });
            setLogs(prev => [...prev, "[FRIDA] Detached."]);
        } catch (error) {
            console.error(error);
        }

        if (fridaWsRef.current) {
            fridaWsRef.current.close();
            fridaWsRef.current = null;
        }
        setIsRunning(false);
    };

    const handleReloadScript = async () => {
        if (!isRunning) {
            setLogs(prev => [...prev, "[RELOAD] ⚠️ No active Frida process. Start the app first."]);
            return;
        }

        setLogs(prev => [...prev, "[RELOAD] 🔄 Re-injecting script into running app..."]);
        setFridaLogs(prev => [...prev, "", "═══════════════════════════════════════════", "🔄 RELOADING SCRIPT", "═══════════════════════════════════════════"]);

        try {
            const response = await fetch('http://localhost:8000/api/frida/reload', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ script: scriptContent })
            });

            const data = await response.json();

            if (data.status === 'reloaded') {
                setLogs(prev => [...prev, "[RELOAD] ✅ Script reloaded successfully!"]);
                setFridaLogs(prev => [...prev, "✅ Script reloaded! Check output above.", "═══════════════════════════════════════════"]);
            } else {
                setLogs(prev => [...prev, `[RELOAD] ❌ Error: ${data.message}`]);
                setFridaLogs(prev => [...prev, `❌ Reload failed: ${data.message}`, "═══════════════════════════════════════════"]);
            }
        } catch (error) {
            setLogs(prev => [...prev, `[RELOAD] ❌ Network error: ${error}`]);
        }
    };

    const connectFridaWs = () => {
        if (fridaWsRef.current) {
            fridaWsRef.current.close();
        }

        // Reset healing trigger for new session
        healingTriggeredRef.current = false;

        const ws = new WebSocket('ws://localhost:8000/ws/frida');

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'log') {
                    const logData = msg.data;
                    setLogs(prev => [...prev, `[SCRIPT] ${logData}`]);
                    setFridaLogs(prev => [...prev.slice(-200), `[LOG] ${logData}`]);

                    // Check for various error patterns and trigger auto-heal
                    // EXCLUDE parsing errors - AI can't fix these (no useful error info)
                    const isParsingError = logData.includes('could not parse') ||
                        logData.includes('expecting');

                    const isError = !isParsingError && (
                        logData.includes('[FRIDA ERROR]') ||
                        logData.includes('TypeError') ||
                        logData.includes('ReferenceError') ||
                        logData.includes('Error:') ||
                        logData.includes('not a function') ||
                        logData.includes('is not defined')
                    );

                    if (isError && !healingTriggeredRef.current) {
                        healingTriggeredRef.current = true;
                        triggerAutoHeal(logData);
                    }

                    // If parsing error, just log it - don't try to heal
                    if (isParsingError) {
                        console.error('[PARSING ERROR] Script has syntax issues - check backend logs');
                        setFridaLogs(prev => [...prev, "⚠️ Script syntax error - check code manually"]);
                    }
                } else if (msg.type === 'error') {
                    const errorData = msg.data;
                    setLogs(prev => [...prev, `[SCRIPT ERROR] ${errorData}`]);
                    setFridaLogs(prev => [...prev.slice(-200), `[ERROR] ${errorData}`]);

                    // Also trigger healing for error type messages
                    if (!healingTriggeredRef.current) {
                        healingTriggeredRef.current = true;
                        triggerAutoHeal(errorData);
                    }
                }
            } catch (e) {
                console.error('Frida WS parse error', e);
            }
        };

        ws.onclose = () => {
            console.log('[Frida WS] Closed');
        };

        fridaWsRef.current = ws;
    };

    // Auto-heal function
    const triggerAutoHeal = async (errorMessage: string) => {
        // Stop the script first
        setIsHealing(true);
        setHealingMessage("🔧 AI ตรวจพบ Error กำลังวิเคราะห์และแก้ไข Script...");
        setLogs(prev => [...prev, "[HEALING] 🔧 AI detected error, attempting to heal script..."]);
        setFridaLogs(prev => [...prev, "", "═══════════════════════════════════════════", "🔧 AI SELF-HEALING MODE ACTIVATED", "═══════════════════════════════════════════"]);

        // Stop the running script
        try {
            await fetch('http://localhost:8000/api/frida/detach', { method: 'POST' });
        } catch (e) {
            console.error('Error stopping script:', e);
        }
        setIsRunning(false);

        // Call healing API
        try {
            const currentScript = scriptContentRef.current;
            console.log('[HEALING] Sending script to AI:', currentScript.substring(0, 100) + '...');
            console.log('[HEALING] History count:', healingHistoryRef.current.length);

            const response = await fetch('http://localhost:8000/api/ai/heal-script', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    error: errorMessage + '\n\n--- FULL RECENT LOGS ---\n' + fridaLogs.slice(-20).join('\n'),
                    script: currentScript,
                    history: healingHistoryRef.current,
                    apk_folder: apkFolderRef.current
                })
            });

            const data = await response.json();
            console.log('[HEALING] AI response:', data);

            // Add this attempt to history
            healingHistoryRef.current = [
                ...healingHistoryRef.current.slice(-4), // Keep last 5 attempts max
                { error: errorMessage.substring(0, 200), script: currentScript.substring(0, 500) }
            ];

            if (data.success && data.healed_script) {
                console.log('[HEALING] Healed script:', data.healed_script.substring(0, 100) + '...');
                setScriptContent(data.healed_script);
                setHealingMessage("✅ Script แก้ไขเรียบร้อย! กด Run เพื่อทดสอบใหม่");
                setLogs(prev => [...prev, "[HEALING] ✅ Script healed successfully!"]);
                setFridaLogs(prev => [...prev, "✅ Script healed! Press Run to test again.", "═══════════════════════════════════════════"]);

                // Clear healing message after 5 seconds
                setTimeout(() => {
                    setHealingMessage("");
                    setIsHealing(false);
                }, 5000);
            } else {
                setHealingMessage("⚠️ ไม่สามารถแก้ไขได้อัตโนมัติ กรุณาตรวจสอบ Error");
                setLogs(prev => [...prev, `[HEALING] ⚠️ Could not auto-heal: ${data.message}`]);
                setFridaLogs(prev => [...prev, "⚠️ Auto-heal failed. Please check error manually.", "═══════════════════════════════════════════"]);

                setTimeout(() => {
                    setHealingMessage("");
                    setIsHealing(false);
                }, 5000);
            }
        } catch (error) {
            setHealingMessage("❌ Network error ไม่สามารถเชื่อมต่อ AI ได้");
            setLogs(prev => [...prev, `[HEALING] ❌ Network error: ${error}`]);

            setTimeout(() => {
                setHealingMessage("");
                setIsHealing(false);
            }, 5000);
        }
    };

    const handleSend = () => {
        if (!input.trim()) return;
        handleGenerateScript();
    };

    const handleGenerateReport = async () => {
        setIsGeneratingReport(true);
        setLogs(prev => [...prev, "[REPORT] กำลังสร้าง Penetration Test Report..."]);

        try {
            const recentLogs = fridaLogs.slice(-30).join('\n');

            const response = await fetch('http://localhost:8000/api/ai/generate-report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    script: scriptContent,
                    frida_logs: recentLogs
                })
            });

            const data = await response.json();

            if (data.success) {
                setLogs(prev => [...prev, `[REPORT] ✓ Report สร้างสำเร็จ! Score: ${data.score}/10 - โปรดตรวจสอบในหน้า Report History`]);
            } else {
                setLogs(prev => [...prev, `[REPORT] ❌ Error: ${data.error || 'Unknown error'}`]);
            }
        } catch (error) {
            setLogs(prev => [...prev, `[REPORT] ❌ Network error: ${error}`]);
        }

        setIsGeneratingReport(false);
    };

    // Keep scriptContentRef in sync with scriptContent state
    useEffect(() => {
        scriptContentRef.current = scriptContent;
    }, [scriptContent]);

    // Keep apkFolderRef in sync with currentApkFolder state
    useEffect(() => {
        apkFolderRef.current = currentApkFolder;
    }, [currentApkFolder]);

    // Load pending script from localStorage (from /analysis redirect)
    useEffect(() => {
        const pendingScript = localStorage.getItem("pendingScript");
        const pendingPackage = localStorage.getItem("pendingPackage");
        const pendingAnalysis = localStorage.getItem("pendingAnalysis");
        const pendingApkFolder = localStorage.getItem("pendingApkFolder");

        if (pendingScript) {
            setScriptContent(pendingScript);
            setLogs(prev => [...prev, "[AI] ✓ Script loaded from analysis."]);
            localStorage.removeItem("pendingScript");
        }

        if (pendingPackage) {
            setTargetPackage(pendingPackage);
            setLogs(prev => [...prev, `[AI] Target package set: ${pendingPackage}`]);
            localStorage.removeItem("pendingPackage");
        }

        if (pendingApkFolder) {
            setCurrentApkFolder(pendingApkFolder);
            console.log('[CONTEXT] APK folder set:', pendingApkFolder);
            localStorage.removeItem("pendingApkFolder");
        }

        if (pendingAnalysis) {
            setLogs(prev => [...prev, `[AI] ${pendingAnalysis}`]);
            localStorage.removeItem("pendingAnalysis");
        }
    }, []);


    // Auto-scroll AI logs
    useEffect(() => {
        if (editorScrollRef.current) {
            const viewport = editorScrollRef.current.querySelector('[data-radix-scroll-area-viewport]');
            if (viewport) viewport.scrollTop = viewport.scrollHeight;
        }
    }, [logs]);

    // Auto-scroll Logcat logs
    useEffect(() => {
        // Use a slight timeout to allow rendering
        setTimeout(() => {
            if (logcatScrollRef.current) {
                logcatScrollRef.current.scrollTop = logcatScrollRef.current.scrollHeight;
            }
        }, 50);
    }, [logcatLogs]);

    // Flush logs to state every 100ms to allow UI updates (prevents freeze on high-volume logs)
    useEffect(() => {
        const interval = setInterval(() => {
            if (logBufferRef.current.length > 0) {
                setLogcatLogs(prev => {
                    const newLogs = [...prev, ...logBufferRef.current];
                    // Keep last 500 lines only to save memory/DOM
                    if (newLogs.length > 500) return newLogs.slice(newLogs.length - 500);
                    return newLogs;
                });
                logBufferRef.current = [];
            }
        }, 100);
        return () => clearInterval(interval);
    }, []);

    const startLogcat = (filter: string = "all") => {
        if (logcatWsRef.current) logcatWsRef.current.close();
        setLogcatLogs([]);
        logBufferRef.current = [];

        try {
            const ws = new WebSocket("ws://localhost:8000/ws/device/logcat");
            ws.onopen = () => {
                ws.send(`filter:${filter}`);
                addLog(`[SYSTEM] Starting Logcat stream (Filter: ${filter})...`);
            };
            ws.onmessage = (event) => {
                // Determine if we should add to buffer
                // Simple filter logic could go here if needed
                logBufferRef.current.push(event.data);
            };
            ws.onclose = () => {
                // Optional
            };
            logcatWsRef.current = ws;
        } catch (e) {
            console.error(e);
        }
    };

    // Handle Tab Change
    // Handle Tab Change
    // Logcat now runs in background on page load, so tab switching doesn't need to manage WS
    useEffect(() => {
        startLogcat("all");

        return () => {
            if (logcatWsRef.current) logcatWsRef.current.close();
        };
    }, []); // Run once on mount


    return (
        <div className="flex h-screen bg-[#0B0E14] text-white font-sans overflow-hidden">
            <Sidebar />

            <main className="flex-1 flex flex-col h-full min-w-0">
                {/* Header */}
                <header className="h-16 border-b border-white/5 flex items-center justify-between px-6 bg-[#0B0E14] z-10 flex-shrink-0">
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2">
                            <Terminal className="w-5 h-5 text-blue-500" />
                            <h1 className="text-lg font-semibold">Script Editor & Analysis</h1>
                        </div>
                    </div>

                    <div className="flex gap-3">
                        <input
                            type="text"
                            placeholder="com.example.app"
                            value={targetPackage}
                            onChange={(e) => setTargetPackage(e.target.value)}
                            className="px-3 py-1 rounded-lg bg-white/5 border border-white/10 text-sm text-white placeholder:text-gray-500 w-48 focus:outline-none focus:border-blue-500"
                        />
                        <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/5 text-xs text-gray-400">
                            <Activity className={`w-3 h-3 ${isRunning ? 'text-emerald-500 animate-pulse' : 'text-gray-500'}`} />
                            <span>{isRunning ? 'Script Running' : 'Ready'}</span>
                        </div>
                        <Button
                            size="sm"
                            variant="secondary"
                            className="bg-amber-600/20 hover:bg-amber-600/30 text-amber-400 border border-amber-500/30"
                            onClick={handleGenerateReport}
                            disabled={isGeneratingReport}
                        >
                            {isGeneratingReport ? (
                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                            ) : (
                                <ClipboardList className="w-4 h-4 mr-2" />
                            )}
                            Report
                        </Button>
                        {isRunning ? (
                            <>
                                <Button
                                    size="sm"
                                    className="bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-900/20"
                                    onClick={handleReloadScript}
                                    title="Re-inject script into running app"
                                >
                                    🔄 Reload
                                </Button>
                                <Button
                                    size="sm"
                                    className="bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-900/20"
                                    onClick={handleStopScript}
                                >
                                    <Square className="w-4 h-4 mr-2" /> Stop
                                </Button>
                            </>
                        ) : (
                            <Button
                                size="sm"
                                className="bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/20"
                                onClick={handleRunScript}
                            >
                                <Play className="w-4 h-4 mr-2" /> Run
                            </Button>
                        )}
                    </div>
                </header>

                <div className="flex-1 grid grid-cols-2 min-h-0 bg-[#0B0E14]">
                    {/* LEFT COLUMN: Tabs Container */}
                    <div className="flex flex-col border-r border-white/5 min-w-0 overflow-hidden">
                        <Tabs value={currentTab} onValueChange={setCurrentTab} className="flex-1 flex flex-col min-h-0">
                            <div className="px-4 py-2 border-b border-white/5 bg-[#0B0E14]">
                                <TabsList className="bg-white/5 border border-white/5 w-full justify-start">
                                    <TabsTrigger value="editor" className="flex-1 data-[state=active]:bg-blue-600">
                                        <Terminal className="w-4 h-4 mr-2" /> Script Editor
                                    </TabsTrigger>
                                    <TabsTrigger value="frida" className="flex-1 data-[state=active]:bg-emerald-600">
                                        <Activity className="w-4 h-4 mr-2" /> Frida Log
                                    </TabsTrigger>
                                    <TabsTrigger value="logcat" className="flex-1 data-[state=active]:bg-blue-600">
                                        <FileText className="w-4 h-4 mr-2" /> Logcat Stream
                                    </TabsTrigger>
                                </TabsList>
                            </div>

                            {/* TAB: EDITOR */}
                            {currentTab === 'editor' && (
                                <div className="flex-1 flex flex-col min-h-0">
                                    {/* Code Editor */}
                                    <div className="flex-1 flex flex-col p-0 min-h-0 relative group">
                                        <div className="absolute top-2 right-4 z-10 opacity-0 group-hover:opacity-100 transition-opacity">
                                            <span className="text-xs text-gray-500 font-mono">current_script.js</span>
                                        </div>
                                        <div className="h-full w-full overflow-auto custom-scrollbar bg-[#0B0E14]">
                                            <CodeHighlighter
                                                code={scriptContent}
                                                onCodeChange={setScriptContent}
                                                language="javascript"
                                            />
                                        </div>
                                    </div>

                                    {/* AI Chat / Logs */}
                                    <div className="h-[35%] flex flex-col border-t border-white/5 bg-[#12141C] overflow-hidden min-h-0">
                                        <ScrollArea className="flex-1 p-4 overflow-auto" ref={editorScrollRef}>
                                            <div className="space-y-3 font-mono text-sm">
                                                {logs.map((log, i) => (
                                                    <div key={i}>
                                                        {log.startsWith(">") ? (
                                                            <span className="text-gray-500">{log}</span>
                                                        ) : (
                                                            <span className="text-blue-400">{log}</span>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        </ScrollArea>

                                        <div className="p-3 bg-white/[0.02] border-t border-white/5">
                                            <div className="flex items-center gap-2 bg-[#0B0E14] border border-white/10 rounded-lg p-2">
                                                <Button size="icon" variant="ghost" className="h-8 w-8 text-gray-500 hover:text-white">
                                                    <Paperclip className="h-4 w-4" />
                                                </Button>
                                                <input
                                                    className="flex-1 bg-transparent border-none outline-none text-sm text-white placeholder:text-gray-600"
                                                    placeholder="Ask AI to modify this script..."
                                                    value={input}
                                                    onChange={(e) => setInput(e.target.value)}
                                                    onKeyDown={(e) => e.key === "Enter" && handleSend()}
                                                />
                                                <Button size="icon" variant="ghost" onClick={handleSend} className="h-8 w-8 text-blue-500 hover:text-blue-400">
                                                    <Send className="h-4 w-4" />
                                                </Button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* TAB: FRIDA CLI */}
                            {currentTab === 'frida' && (
                                <div className="flex-1 flex flex-col min-h-0 bg-[#1a1c23]">
                                    {/* Terminal Header */}
                                    <div className="px-4 py-2 bg-[#0d0f12] flex justify-between items-center text-xs font-mono border-b border-white/10">
                                        <div className="flex items-center gap-3">
                                            <div className="flex gap-1.5">
                                                <span className="w-3 h-3 rounded-full bg-red-500"></span>
                                                <span className="w-3 h-3 rounded-full bg-yellow-500"></span>
                                                <span className="w-3 h-3 rounded-full bg-green-500"></span>
                                            </div>
                                            <span className="text-gray-400">Frida CLI</span>
                                        </div>
                                        <div className="flex gap-2">
                                            <Button variant="ghost" size="sm" onClick={() => setFridaLogs([])} className="h-6 text-gray-400 hover:text-white">Clear</Button>
                                            <span className="flex items-center gap-2 text-emerald-400">
                                                <span className={`w-2 h-2 rounded-full ${isRunning ? 'bg-emerald-500 animate-pulse' : 'bg-gray-500'}`} />
                                                {isRunning ? 'Connected' : 'Disconnected'}
                                            </span>
                                        </div>
                                    </div>

                                    {/* Healing Status Banner */}
                                    {healingMessage && (
                                        <div className={`px-4 py-3 border-b border-white/10 flex items-center gap-3 ${healingMessage.includes('✅') ? 'bg-emerald-500/20 text-emerald-300' :
                                            healingMessage.includes('⚠️') ? 'bg-yellow-500/20 text-yellow-300' :
                                                healingMessage.includes('❌') ? 'bg-red-500/20 text-red-300' :
                                                    'bg-purple-500/20 text-purple-300'
                                            }`}>
                                            {isHealing && !healingMessage.includes('✅') && (
                                                <Loader2 className="w-4 h-4 animate-spin" />
                                            )}
                                            <span className="font-medium">{healingMessage}</span>
                                        </div>
                                    )}

                                    {/* Terminal Output - preserve whitespace for ASCII art */}
                                    <pre
                                        className="flex-1 overflow-auto p-4 custom-scrollbar font-mono text-sm bg-[#1a1c23] m-0"
                                        ref={fridaLogScrollRef}
                                    >
                                        {fridaLogs.length === 0 && (
                                            <span className="text-gray-600 italic">
                                                Waiting for Frida... Click "Run" to start.
                                            </span>
                                        )}
                                        {fridaLogs.map((line, i) => (
                                            <div
                                                key={i}
                                                className={`${line.includes('[ERROR]') || line.includes('Error')
                                                    ? 'text-red-400'
                                                    : line.includes('SELF-HEALING') || line.includes('🔧')
                                                        ? 'text-purple-400 font-bold'
                                                        : line.includes('healed') || line.includes('✅')
                                                            ? 'text-emerald-400 font-bold'
                                                            : line.includes('═══')
                                                                ? 'text-purple-300'
                                                                : line.includes('[BYPASS]')
                                                                    ? 'text-emerald-400 font-bold'
                                                                    : line.includes('[DUMP]') || line.includes('Correct answer')
                                                                        ? 'text-yellow-400 font-bold'
                                                                        : line.startsWith('$')
                                                                            ? 'text-green-400'
                                                                            : line.includes('Frida') || line.includes('____') || line.includes('/_/')
                                                                                ? 'text-cyan-400'
                                                                                : line.includes('::') || line.includes(']->')
                                                                                    ? 'text-blue-400'
                                                                                    : 'text-gray-300'
                                                    }`}
                                            >
                                                {line}
                                            </div>
                                        ))}
                                    </pre>

                                    {/* Terminal Input */}
                                    <div className="p-2 bg-[#0d0f12] border-t border-white/10">
                                        <div className="flex items-center gap-2 bg-[#1a1c23] rounded px-3 py-2">
                                            <span className="text-emerald-500 font-mono">→</span>
                                            <input
                                                type="text"
                                                value={fridaInput}
                                                onChange={(e) => setFridaInput(e.target.value)}
                                                onKeyDown={async (e) => {
                                                    if (e.key === 'Enter' && fridaInput.trim()) {
                                                        const cmd = fridaInput.trim();
                                                        setFridaLogs(prev => [...prev, `> ${cmd}`]);

                                                        // Handle exit/quit commands
                                                        if (cmd === 'exit' || cmd === 'quit') {
                                                            try {
                                                                await fetch('http://localhost:8000/api/frida/detach', { method: 'POST' });
                                                                setFridaLogs(prev => [...prev, '[Frida] Session terminated.']);
                                                            } catch (err) {
                                                                console.error(err);
                                                            }
                                                            setIsRunning(false);
                                                            setFridaInput("");
                                                            return;
                                                        }

                                                        // Send command to Frida
                                                        try {
                                                            await fetch('http://localhost:8000/api/frida/input', {
                                                                method: 'POST',
                                                                headers: { 'Content-Type': 'application/json' },
                                                                body: JSON.stringify({ command: cmd })
                                                            });
                                                        } catch (err) {
                                                            setFridaLogs(prev => [...prev, `[ERROR] ${err}`]);
                                                        }
                                                        setFridaInput("");
                                                    }
                                                }}
                                                placeholder={isRunning ? "Type command (e.g., help, %resume, exit)..." : "Start Frida first..."}
                                                disabled={!isRunning}
                                                className="flex-1 bg-transparent border-none outline-none text-sm text-white font-mono placeholder:text-gray-600"
                                            />
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* TAB: LOGCAT */}
                            {currentTab === 'logcat' && (
                                <div className="flex-1 flex flex-col min-h-0 bg-[#0B0E14]">
                                    <div className="px-4 py-2 bg-white/5 flex justify-between items-center text-xs font-mono border-b border-white/5">
                                        <span className="text-gray-400">adb logcat</span>
                                        <div className="flex gap-2">
                                            <Button variant="ghost" size="sm" onClick={() => setLogcatLogs([])} className="h-6 text-gray-400 hover:text-white">Clear</Button>
                                            <span className="flex items-center gap-2 text-emerald-400">
                                                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" /> Live
                                            </span>
                                        </div>
                                    </div>
                                    {/* Using native div for fast scrolling of large logs */}
                                    <div
                                        className="flex-1 overflow-auto p-4 custom-scrollbar font-mono text-xs space-y-1"
                                        ref={logcatScrollRef}
                                    >
                                        {logcatLogs.length === 0 && (
                                            <div className="text-gray-600 italic p-4 text-center">Waiting for logs...</div>
                                        )}
                                        {logcatLogs.map((line, i) => (
                                            <div key={i} className="text-gray-300 hover:bg-white/5 px-1 rounded break-all leading-tight truncate">
                                                {line}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </Tabs>
                    </div>

                    {/* RIGHT COLUMN: Device Screen Mirror */}
                    <div className="flex flex-col items-center justify-center bg-black/40 p-8 relative overflow-hidden">
                        {/* Background Decoration */}
                        <div className="absolute inset-0 bg-[url('https://images.unsplash.com/photo-1601784551446-20c9e07cdbdb?q=80&w=2667&auto=format&fit=crop')] bg-cover bg-center opacity-5 blur-xl"></div>

                        {/* Phone Container */}
                        <div className="relative z-10 h-[90%] aspect-[9/19] rounded-[2.5rem] border-[8px] border-[#1a1c23] shadow-2xl bg-black overflow-hidden ring-1 ring-white/10">
                            {/* Camera Notch */}
                            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-1/3 h-6 bg-[#1a1c23] rounded-b-xl z-20"></div>

                            {/* MJPEG Stream via img tag */}
                            <img
                                ref={imgRef}
                                src="http://localhost:8000/video_feed"
                                className="h-full w-full object-cover cursor-pointer select-none"
                                alt="Device Screen Stream"
                                draggable={false}
                                onDragStart={(e) => e.preventDefault()}
                                onLoad={() => setIsConnected(true)}
                                onError={() => setIsConnected(false)}
                                onMouseDown={(e) => {
                                    const rect = e.currentTarget.getBoundingClientRect();
                                    e.currentTarget.dataset.startX = (e.clientX - rect.left).toString();
                                    e.currentTarget.dataset.startY = (e.clientY - rect.top).toString();
                                    e.currentTarget.dataset.startTime = Date.now().toString();
                                }}
                                onMouseUp={async (e) => {
                                    const startX = parseFloat(e.currentTarget.dataset.startX || "0");
                                    const startY = parseFloat(e.currentTarget.dataset.startY || "0");
                                    const startTime = parseFloat(e.currentTarget.dataset.startTime || "0");

                                    const rect = e.currentTarget.getBoundingClientRect();
                                    const endX = e.clientX - rect.left;
                                    const endY = e.clientY - rect.top;

                                    // Scale to device coordinates (assume 1080x2400)
                                    const DEVICE_WIDTH = 1080;
                                    const DEVICE_HEIGHT = 2400;
                                    const scaleX = DEVICE_WIDTH / rect.width;
                                    const scaleY = DEVICE_HEIGHT / rect.height;

                                    const x1 = Math.round(startX * scaleX);
                                    const y1 = Math.round(startY * scaleY);
                                    const x2 = Math.round(endX * scaleX);
                                    const y2 = Math.round(endY * scaleY);

                                    const distance = Math.hypot(x2 - x1, y2 - y1);
                                    const duration = Date.now() - startTime;

                                    if (distance < 20) {
                                        try {
                                            await fetch('http://localhost:8000/api/input/tap', {
                                                method: 'POST',
                                                headers: { 'Content-Type': 'application/json' },
                                                body: JSON.stringify({ x: x1, y: y1 }),
                                            });
                                        } catch (err) { console.error(err); }
                                    } else {
                                        try {
                                            await fetch('http://localhost:8000/api/input/swipe', {
                                                method: 'POST',
                                                headers: { 'Content-Type': 'application/json' },
                                                body: JSON.stringify({ x1, y1, x2, y2, duration: Math.max(duration, 100) }),
                                            });
                                        } catch (err) { console.error(err); }
                                    }
                                }}
                            />

                            {/* Fallback when not connected */}
                            {!isConnected && (
                                <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-600 bg-black/80">
                                    <Smartphone className="w-12 h-12 mb-2 opacity-50 animate-pulse" />
                                    <p className="text-xs font-mono">Connecting...</p>
                                </div>
                            )}
                        </div>

                        <div className="absolute bottom-6 text-center">
                            <p className="text-xs text-gray-500 font-mono">
                                {isConnected ? (
                                    <span className="text-emerald-400">● Live Mirror (MJPEG)</span>
                                ) : (
                                    <span className="text-yellow-400">○ Connecting...</span>
                                )}
                            </p>
                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
}

"use client";

import { useState, useEffect } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Folder, FileCode, ChevronRight, ChevronDown, Search, ArrowRight, Upload, Play, Box, AlertTriangle, X, Shield, Cpu } from "lucide-react";
import { useWebSocket } from "@/components/providers/WebSocketProvider";
import CodeHighlighter, { detectLanguage } from "@/components/ui/CodeHighlighter";

// Types
interface FileNode {
    name: string;
    type: 'dir' | 'file';
    children?: FileNode[];
    path: string;
}

export default function AnalysisPage() {
    const { logs, addLog } = useWebSocket();

    const [fileTree, setFileTree] = useState<FileNode[]>([]);
    const [selectedFile, setSelectedFile] = useState<string | null>(null);
    const [fileContent, setFileContent] = useState<string>("Select a file to view its content...");
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [currentApk, setCurrentApk] = useState<string | null>(null);

    // Native detection states
    const [showNativeAlert, setShowNativeAlert] = useState(false);
    const [detectedNativeLibs, setDetectedNativeLibs] = useState<any[]>([]);
    const [isDeepAnalyzing, setIsDeepAnalyzing] = useState(false);

    // Load selected APK from dashboard (localStorage)
    useEffect(() => {
        const selectedApkJson = localStorage.getItem("selectedApk");
        if (selectedApkJson) {
            try {
                const apk = JSON.parse(selectedApkJson);
                // Clear localStorage to prevent re-loading on refresh
                localStorage.removeItem("selectedApk");

                // Load the APK's file tree
                loadExistingApk(apk.name);
            } catch (e) {
                console.error("Failed to load selected APK:", e);
            }
        }
    }, []);

    const loadExistingApk = async (apkName: string) => {
        setCurrentApk(apkName);
        addLog(`[SYSTEM] Loading ${apkName}...`);

        try {
            // Use /api/apks/load to load existing folder without re-decompiling
            const res = await fetch("http://localhost:8000/api/apks/load", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ folder_name: apkName })
            });
            const data = await res.json();

            if (data.file_tree) {
                setFileTree(data.file_tree);
                addLog(`[SUCCESS] Loaded ${data.package_name}`);
                if (data.manifest_xml) {
                    setFileContent(data.manifest_xml);
                    setSelectedFile("AndroidManifest.xml");
                }
            } else if (data.error) {
                addLog(`[ERROR] ${data.error}`);
            }
        } catch (err) {
            addLog(`[ERROR] Failed to load: ${err}`);
        }
    };


    const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        if (!e.target.files?.[0]) return;
        setUploading(true);
        const file = e.target.files[0];
        const formData = new FormData();
        formData.append("file", file);

        try {
            // 1. Upload
            const res = await fetch("http://localhost:8000/upload", {
                method: "POST",
                body: formData
            });
            const data = await res.json();
            const uploadedFilename = data.filename || file.name;
            setCurrentApk(uploadedFilename);

            // 2. Trigger Analysis
            addLog(`[SYSTEM] Uploaded ${uploadedFilename}. Starting analysis...`);
            const analyzeRes = await fetch("http://localhost:8000/api/analyze", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ filename: uploadedFilename })
            });
            const analyzeData = await analyzeRes.json();

            if (analyzeData.file_tree) {
                setFileTree(analyzeData.file_tree);
                addLog(`[SUCCESS] Analysis complete. Found ${analyzeData.package_name}`);
                if (analyzeData.manifest_xml) {
                    setFileContent(analyzeData.manifest_xml);
                    setSelectedFile("AndroidManifest.xml");
                }

                // Simplified Warning Log
                if (analyzeData.warnings) {
                    addLog(`[INFO] Decompilation completed (partial success). Some errors were ignored.`);
                }
            } else {
                const errorMsg = analyzeData.details ? `${analyzeData.error}: ${analyzeData.details}` : analyzeData.error;
                addLog(`[ERROR] Analysis failed: ${errorMsg}`);
            }
        } catch (err) {
            console.error(err);
            addLog(`[ERROR] ${err}`);
        } finally {
            setUploading(false);
        }
    };

    const fetchFileContent = async (path: string) => {
        if (!currentApk) return;
        setFileContent("Loading...");
        try {
            const res = await fetch("http://localhost:8000/api/analyze/file", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ apk_name: currentApk, file_path: path })
            });
            const data = await res.json();
            if (data.content) {
                setFileContent(data.content);
            } else {
                setFileContent(`// Error: ${data.error}`);
            }
        } catch (e) {
            setFileContent(`// Fetch Error: ${e}`);
        }
    };

    const handleGenerate = async () => {
        if (!currentApk) {
            addLog("[ERROR] Please upload an APK first.");
            return;
        }

        setIsAnalyzing(true);
        addLog(`[AI] Analyzing ${currentApk} for vulnerabilities...`);

        try {
            const response = await fetch("http://localhost:8000/api/ai/auto-generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ apk_name: currentApk })
            });

            const data = await response.json();

            // Check for native library detection
            if (data.native_detected) {
                if (data.flutter_detected) {
                    addLog(`[NATIVE] 🦋 Flutter app detected!`);
                    addLog(`[NATIVE] ⚠️ libflutter.so skipped (Flutter engine — not developer code)`);
                    addLog(`[NATIVE] 🔍 Focusing on: ${data.native_libs.map((l: any) => l.so_file).join(", ")} (contains Dart business logic)`);
                } else {
                    addLog(`[NATIVE] 🔍 Detected native libraries: ${data.native_libs.map((l: any) => l.so_file).join(", ")}`);
                }
                setDetectedNativeLibs(data.native_libs);
                setShowNativeAlert(true);
                setIsAnalyzing(false);
                return;
            }

            if (data.success && data.script) {
                addLog(`[AI] ✓ Analysis complete! Found hooks for ${data.package}`);
                addLog(`[AI] ${data.analysis || 'No analysis provided'}`);

                // Store in localStorage for editor page
                localStorage.setItem("pendingScript", data.script);
                localStorage.setItem("pendingPackage", data.package || "");
                localStorage.setItem("pendingAnalysis", data.analysis || "");
                localStorage.setItem("pendingApkFolder", currentApk || "");

                addLog(`[AI] Redirecting to Editor...`);
                setTimeout(() => { window.location.href = "/editor"; }, 1000);
            } else {
                addLog(`[ERROR] ${data.error || data.analysis || 'Unknown error'}`);
            }
        } catch (error) {
            addLog(`[ERROR] API call failed: ${error}`);
        } finally {
            setIsAnalyzing(false);
        }
    };

    // Deep Analysis — r2pipe recon + AI
    const handleDeepAnalysis = async () => {
        setShowNativeAlert(false);
        setIsDeepAnalyzing(true);
        addLog(`[NATIVE] 🔬 Starting deep native analysis...`);
        addLog(`[NATIVE] ⏳ Running r2pipe reconnaissance (this may take a moment)...`);

        try {
            const response = await fetch("http://localhost:8000/api/ai/native-deep-analysis", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    apk_name: currentApk,
                    native_libs: detectedNativeLibs
                })
            });

            const data = await response.json();

            if (data.success && data.script) {
                addLog(`[NATIVE] ✓ Deep analysis complete!`);
                addLog(`[AI] ${data.analysis || 'No analysis provided'}`);

                localStorage.setItem("pendingScript", data.script);
                localStorage.setItem("pendingPackage", data.package || "");
                localStorage.setItem("pendingAnalysis", data.analysis || "");
                localStorage.setItem("pendingApkFolder", currentApk || "");

                addLog(`[AI] Redirecting to Editor...`);
                setTimeout(() => { window.location.href = "/editor"; }, 1000);
            } else {
                addLog(`[ERROR] Deep analysis failed: ${data.error || 'Unknown error'}`);
            }
        } catch (error) {
            addLog(`[ERROR] Deep analysis API call failed: ${error}`);
        } finally {
            setIsDeepAnalyzing(false);
        }
    };

    // Skip — generate standard Frida script
    const handleSkipNative = async () => {
        setShowNativeAlert(false);
        setIsAnalyzing(true);
        addLog(`[AI] Skipping native analysis, generating standard Frida script...`);

        try {
            const response = await fetch("http://localhost:8000/api/ai/skip-native", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ apk_name: currentApk })
            });

            const data = await response.json();

            if (data.success && data.script) {
                addLog(`[AI] ✓ Analysis complete! Found hooks for ${data.package}`);

                localStorage.setItem("pendingScript", data.script);
                localStorage.setItem("pendingPackage", data.package || "");
                localStorage.setItem("pendingAnalysis", data.analysis || "");
                localStorage.setItem("pendingApkFolder", currentApk || "");

                addLog(`[AI] Redirecting to Editor...`);
                setTimeout(() => { window.location.href = "/editor"; }, 1000);
            } else {
                addLog(`[ERROR] ${data.error || 'Unknown error'}`);
            }
        } catch (error) {
            addLog(`[ERROR] Skip native API call failed: ${error}`);
        } finally {
            setIsAnalyzing(false);
        }
    };


    // Recursive File Tree Component
    const FileTreeItem = ({ node, level = 0, onFileSelect }: { node: FileNode, level?: number, onFileSelect: (path: string) => void }) => {
        const [isOpen, setIsOpen] = useState(false);
        const indent = level * 12;

        return (
            <div>
                <div
                    className={`flex items-center gap-2 py-1 px-2 hover:bg-white/5 cursor-pointer text-sm ${selectedFile === node.path ? 'bg-blue-500/10 text-blue-400' : 'text-gray-400'}`}
                    style={{ paddingLeft: `${indent + 8}px` }}
                    onClick={async () => {
                        if (node.type === 'dir') {
                            setIsOpen(!isOpen);
                        } else {
                            setSelectedFile(node.path);
                            onFileSelect(node.path);
                        }
                    }}
                >
                    {node.type === 'dir' ? (
                        isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />
                    ) : (
                        <FileCode className="w-4 h-4" />
                    )}
                    {node.type === 'dir' ? <Folder className="w-4 h-4 text-yellow-500/80" /> : null}
                    <span>{node.name}</span>
                </div>
                {isOpen && node.children && (
                    <div>
                        {node.children.map((child, i) => (
                            <FileTreeItem key={i} node={child} level={level + 1} onFileSelect={onFileSelect} />
                        ))}
                    </div>
                )}
            </div>
        );
    };

    return (
        <div className="flex h-screen bg-[#0B0E14] text-white font-sans overflow-hidden">
            <Sidebar />

            <main className="flex-1 flex flex-col min-w-0">
                {/* Header */}
                <header className="h-16 border-b border-white/5 flex items-center justify-between px-6 bg-[#0B0E14]">
                    <h1 className="text-lg font-semibold flex items-center gap-2">
                        <Box className="text-blue-500" /> APK Analysis
                    </h1>
                    <div className="flex items-center gap-3">
                        <Button variant="outline" className="border-white/10 text-gray-400 hover:text-white" onClick={() => document.getElementById('apk-upload')?.click()}>
                            <Upload className="w-4 h-4 mr-2" />
                            {uploading ? "Uploading..." : "Upload APK"}
                        </Button>
                        <input type="file" id="apk-upload" accept=".apk" className="hidden" onChange={handleUpload} />

                        <Button className="bg-blue-600 hover:bg-blue-500" onClick={handleGenerate} disabled={isAnalyzing}>
                            <Play className="w-4 h-4 mr-2" /> Generate Hook
                        </Button>
                    </div>
                </header>

                <div className="flex-1 flex min-h-0">
                    {/* Left: File Tree */}
                    <div className="w-80 border-r border-white/5 flex flex-col bg-[#0F1117]">
                        <div className="p-4 border-b border-white/5">
                            <div className="relative">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3 w-3 text-gray-500" />
                                <input className="w-full bg-[#1A1D24] rounded-lg py-1.5 pl-8 text-xs text-white border border-white/5 focus:outline-none" placeholder="Search files..." />
                            </div>
                        </div>
                        <ScrollArea className="flex-1">
                            {fileTree.length > 0 ? (
                                <div className="py-2">
                                    {fileTree.map((node, i) => (
                                        <FileTreeItem
                                            key={i}
                                            node={node}
                                            onFileSelect={fetchFileContent}
                                        />
                                    ))}
                                </div>
                            ) : (
                                <div className="text-center p-8 text-gray-600 text-xs">
                                    No APK loaded. <br /> Upload a file to start.
                                </div>
                            )}
                        </ScrollArea>
                    </div>

                    {/* Middle: Content Viewer */}
                    <div className="flex-1 flex flex-col min-w-0 bg-[#0B0E14]">
                        <div className="h-10 border-b border-white/5 flex items-center px-4 justify-between bg-[#0F1117]">
                            <span className="text-xs font-mono text-gray-400">{selectedFile || "No file selected"}</span>
                        </div>
                        {/* Code viewer with syntax highlighting */}
                        <div className="flex-1 overflow-auto p-4 custom-scrollbar">
                            <CodeHighlighter
                                code={fileContent}
                                language={selectedFile ? detectLanguage(selectedFile) : "java"}
                                readOnly
                            />
                        </div>
                    </div>

                    {/* Right: AI Insights */}
                    <div className="w-96 border-l border-white/5 flex flex-col bg-[#0F1117]">
                        <div className="p-4 border-b border-white/5 font-semibold text-sm">AI Insights</div>
                        <ScrollArea className="flex-1 p-4">
                            <div className="space-y-4">
                                {logs.map((log, i) => (
                                    <div key={i} className={`text-xs p-3 rounded-lg border ${log.includes("ERROR") ? "bg-red-500/10 border-red-500/20 text-red-200" : log.includes("WARNING") ? "bg-yellow-500/10 border-yellow-500/20 text-yellow-200" : "bg-blue-500/5 border-blue-500/10 text-blue-200"}`}>
                                        {log}
                                    </div>
                                ))}
                            </div>
                        </ScrollArea>
                    </div>
                </div>
            </main>

            {/* Native Detection Alert Modal */}
            {showNativeAlert && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
                    <div className="bg-[#0F1117] border border-white/10 rounded-2xl w-[560px] max-h-[80vh] overflow-y-auto shadow-2xl">
                        {/* Header */}
                        <div className="flex items-center justify-between p-5 border-b border-white/10">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-xl bg-amber-500/10 flex items-center justify-center">
                                    <Shield className="w-5 h-5 text-amber-400" />
                                </div>
                                <div>
                                    <h2 className="text-base font-semibold text-white">ARES Detection Alert</h2>
                                    <p className="text-xs text-gray-400">Native Library Detected</p>
                                </div>
                            </div>
                            <button onClick={() => setShowNativeAlert(false)} className="text-gray-500 hover:text-white transition-colors">
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        {/* Body */}
                        <div className="p-5 space-y-4">
                            <p className="text-sm text-gray-300 leading-relaxed">
                                The application dynamically loads a Native Library. Native libraries are frequently used to conceal critical security logic, encryption keys, or anti-tampering mechanisms.
                            </p>

                            {/* Detected Libraries */}
                            <div className="bg-amber-500/5 border border-amber-500/20 rounded-lg p-3">
                                <div className="flex items-center gap-2 mb-2">
                                    <Cpu className="w-4 h-4 text-amber-400" />
                                    <span className="text-xs font-semibold text-amber-400">DETECTED LIBRARIES</span>
                                </div>
                                {detectedNativeLibs.map((lib, i) => (
                                    <div key={i} className="flex items-center gap-2 text-xs text-gray-300 py-1">
                                        <span className="text-amber-400">▸</span>
                                        <code className="bg-black/30 px-2 py-0.5 rounded text-amber-200">{lib.so_file}</code>
                                        <span className="text-gray-500">found in {lib.found_in}</span>
                                    </div>
                                ))}
                            </div>

                            {/* Warning */}
                            <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-3">
                                <div className="flex items-start gap-2">
                                    <AlertTriangle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                                    <p className="text-xs text-red-200/80 leading-relaxed">
                                        <strong>WARNING:</strong> Fully automated AI deep analysis on native code has a high margin of error. Real-world applications often employ complex obfuscation, packing, or anti-analysis techniques that may cause the AI to hallucinate or misinterpret the assembly logic. Manual verification of the results is highly recommended.
                                    </p>
                                </div>
                            </div>

                            <p className="text-sm text-gray-400">
                                Would you like ARES to attempt a deep reverse engineering analysis on this library?
                            </p>
                        </div>

                        {/* Actions */}
                        <div className="p-5 border-t border-white/10 space-y-2">
                            <Button
                                className="w-full bg-amber-600 hover:bg-amber-500 text-white py-2.5"
                                onClick={handleDeepAnalysis}
                            >
                                <Shield className="w-4 h-4 mr-2" />
                                [1] Deep Analysis — Automated Reconnaissance & AI Extraction
                            </Button>
                            <Button
                                variant="outline"
                                className="w-full border-white/10 text-gray-400 hover:text-white py-2.5"
                                onClick={handleSkipNative}
                            >
                                [2] Skip — Generate standard Frida hook script
                            </Button>
                        </div>
                    </div>
                </div>
            )}

            {/* Deep Analysis Loading Overlay */}
            {isDeepAnalyzing && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
                    <div className="bg-[#0F1117] border border-white/10 rounded-2xl p-8 text-center space-y-4 w-[400px]">
                        <div className="w-16 h-16 mx-auto rounded-full bg-amber-500/10 flex items-center justify-center animate-pulse">
                            <Cpu className="w-8 h-8 text-amber-400" />
                        </div>
                        <h3 className="text-lg font-semibold text-white">Deep Native Analysis</h3>
                        <p className="text-sm text-gray-400">
                            🔍 ARES is performing r2pipe reconnaissance on the native library...
                        </p>
                        <div className="flex items-center justify-center gap-2">
                            <div className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                            <div className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                            <div className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                        </div>
                        <p className="text-xs text-gray-500">This may take 30-60 seconds...</p>
                    </div>
                </div>
            )}
        </div>
    );
}

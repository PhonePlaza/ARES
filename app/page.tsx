"use client";

import { useState, useEffect } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Button } from "@/components/ui/button";
import { Activity, Package, Trash2, FolderOpen, HardDrive, FileCode, Clock } from "lucide-react";
import { useWebSocket } from "@/components/providers/WebSocketProvider";
import { useRouter } from "next/navigation";

interface DecompiledApk {
  name: string;
  package: string;
  size_mb: number;
  file_count: number;
  modified: string;
  path: string;
}

export default function Home() {
  const { isConnected } = useWebSocket();
  const router = useRouter();
  const [apks, setApks] = useState<DecompiledApk[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);

  // Fetch decompiled APKs on mount
  useEffect(() => {
    fetchApks();
  }, []);

  const fetchApks = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/apks/list");
      const data = await res.json();
      setApks(data.apks || []);
    } catch (error) {
      console.error("Failed to fetch APKs:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (apk: DecompiledApk) => {
    if (!confirm(`Delete "${apk.name}" and uninstall ${apk.package} from device?`)) {
      return;
    }

    setDeleting(apk.name);
    try {
      const res = await fetch("http://localhost:8000/api/apks/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          folder_name: apk.name,
          package_name: apk.package,
          uninstall: true
        })
      });
      const data = await res.json();
      if (data.status === "deleted") {
        setApks(prev => prev.filter(a => a.name !== apk.name));
      } else {
        alert(`Failed to delete: ${data.message}`);
      }
    } catch (error) {
      alert(`Error: ${error}`);
    } finally {
      setDeleting(null);
    }
  };

  const handleAnalyze = (apk: DecompiledApk) => {
    // Store selected APK info and navigate to analysis
    localStorage.setItem("selectedApk", JSON.stringify(apk));
    router.push("/analysis");
  };

  return (
    <div className="flex h-screen bg-[#0B0E14] text-white font-sans overflow-hidden">
      <Sidebar />

      <main className="flex-1 flex flex-col">
        {/* Header */}
        <header className="h-20 border-b border-white/5 flex items-center justify-between px-8 bg-[#0B0E14]/50 backdrop-blur-sm">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
            <p className="text-sm text-gray-500 flex items-center gap-2">
              System:
              <span className={isConnected ? "text-emerald-500" : "text-rose-500"}>
                {isConnected ? "Online" : "Offline"}
              </span>
            </p>
          </div>
        </header>

        {/* Content */}
        <div className="flex-1 p-8 overflow-auto">
          {/* Frida Core Status */}
          <div className="glass-panel p-6 rounded-2xl bg-gradient-to-b from-blue-900/10 to-transparent mb-8 max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold">Frida Core</h3>
              <Activity className="h-4 w-4 text-blue-400" />
            </div>
            <div className="text-3xl font-bold mb-1">{isConnected ? "Active" : "Idle"}</div>
            <p className="text-xs text-emerald-400 flex items-center gap-1">
              <span className={`h-2 w-2 rounded-full ${isConnected ? "bg-emerald-500 animate-pulse" : "bg-gray-500"}`} />
              {isConnected ? "Backend Connected" : "Waiting for backend..."}
            </p>
          </div>

          {/* Decompiled APKs Section */}
          <div className="mb-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold flex items-center gap-2">
                <Package className="w-5 h-5 text-blue-400" />
                Decompiled APKs
              </h2>
            </div>

            {loading ? (
              <div className="text-gray-500 text-center py-12">Loading...</div>
            ) : apks.length === 0 ? (
              <div className="glass-panel rounded-2xl p-12 text-center">
                <Package className="w-16 h-16 mx-auto mb-4 text-gray-600" />
                <h3 className="text-lg font-medium text-gray-400 mb-2">No APKs Analyzed Yet</h3>
                <p className="text-gray-500 text-sm mb-4">
                  Upload an APK in the Analysis page to get started
                </p>
                <Button
                  onClick={() => router.push("/analysis")}
                  className="bg-blue-600 hover:bg-blue-500"
                >
                  Go to Analysis
                </Button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {apks.map((apk) => (
                  <div
                    key={apk.name}
                    className="glass-panel rounded-xl p-5 border border-white/5 hover:border-blue-500/30 transition-all group"
                  >
                    {/* APK Header */}
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-green-500 to-emerald-600 flex items-center justify-center">
                          <Package className="w-5 h-5 text-white" />
                        </div>
                        <div>
                          <h3 className="font-medium text-sm truncate max-w-[180px]" title={apk.name}>
                            {apk.name}
                          </h3>
                          <p className="text-xs text-gray-500 truncate max-w-[180px]" title={apk.package}>
                            {apk.package}
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* APK Stats */}
                    <div className="grid grid-cols-3 gap-2 mb-4 text-xs">
                      <div className="bg-white/5 rounded-lg p-2 text-center">
                        <HardDrive className="w-3 h-3 mx-auto mb-1 text-gray-400" />
                        <span className="text-gray-300">{apk.size_mb} MB</span>
                      </div>
                      <div className="bg-white/5 rounded-lg p-2 text-center">
                        <FileCode className="w-3 h-3 mx-auto mb-1 text-gray-400" />
                        <span className="text-gray-300">{apk.file_count} files</span>
                      </div>
                      <div className="bg-white/5 rounded-lg p-2 text-center">
                        <Clock className="w-3 h-3 mx-auto mb-1 text-gray-400" />
                        <span className="text-gray-300 text-[10px]">{apk.modified.split(" ")[0]}</span>
                      </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        className="flex-1 bg-blue-600 hover:bg-blue-500"
                        onClick={() => handleAnalyze(apk)}
                      >
                        <FolderOpen className="w-4 h-4 mr-1" />
                        Analyze
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="border-red-500/30 text-red-400 hover:bg-red-500/20 hover:border-red-500"
                        onClick={() => handleDelete(apk)}
                        disabled={deleting === apk.name}
                      >
                        {deleting === apk.name ? (
                          <span className="animate-spin">⏳</span>
                        ) : (
                          <Trash2 className="w-4 h-4" />
                        )}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

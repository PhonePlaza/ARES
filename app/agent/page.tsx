"use client";

"use client";

import { useEffect, useState, useRef } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Activity, Search, Server, Cpu, Smartphone, FileText, Filter, Terminal } from "lucide-react";
import { useWebSocket } from "@/components/providers/WebSocketProvider";

interface Process {
    pid: number | string;
    name: string;
    identifier?: string;
}

export default function LiveAgentPage() {
    const { addLog } = useWebSocket();
    const [mode, setMode] = useState("processes"); // processes, apps
    const [items, setItems] = useState<Process[]>([]);
    const [search, setSearch] = useState("");
    const [loading, setLoading] = useState(false);

    const fetchData = async () => {
        setLoading(true);
        setItems([]);
        const endpoint = mode === "apps" ? "http://localhost:8000/api/device/apps" : "http://localhost:8000/api/processes";
        try {
            const res = await fetch(endpoint);
            const data = await res.json();
            if (Array.isArray(data)) {
                setItems(data);
            }
        } catch (e) {
            console.error(e);
            addLog(`[ERROR] Failed to fetch device data: ${e}`);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, [mode]);

    const filteredItems = items.filter(p =>
        p.name.toLowerCase().includes(search.toLowerCase()) ||
        p.pid.toString().includes(search) ||
        (p.identifier && p.identifier.toLowerCase().includes(search.toLowerCase()))
    );

    return (
        <div className="flex h-screen bg-[#0B0E14] text-white font-sans overflow-hidden">
            <Sidebar />
            <main className="flex-1 flex flex-col h-full p-6 min-w-0">
                <header className="flex items-center justify-between mb-4 flex-shrink-0">
                    <div>
                        <h1 className="text-xl font-bold flex items-center gap-2">
                            <Activity className="text-blue-500 w-5 h-5" /> Live Device Monitor
                        </h1>
                    </div>
                </header>

                <Tabs value={mode} onValueChange={setMode} className="flex-1 flex flex-col min-h-0">
                    <div className="flex items-center justify-between mb-4 flex-shrink-0">
                        <TabsList className="bg-[#12141C] border border-white/10">
                            <TabsTrigger value="processes" className="data-[state=active]:bg-blue-600">
                                <Cpu className="w-4 h-4 mr-2" /> Processes
                            </TabsTrigger>
                            <TabsTrigger value="apps" className="data-[state=active]:bg-blue-600">
                                <Smartphone className="w-4 h-4 mr-2" /> Installed Apps
                            </TabsTrigger>
                        </TabsList>

                        <div className="flex gap-2">
                            <Button onClick={fetchData} disabled={loading} size="sm" className="bg-white/5 hover:bg-white/10">
                                {loading ? "Scanning..." : "Refresh"}
                            </Button>
                        </div>
                    </div>

                    <div className="relative mb-3 flex-shrink-0">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
                        <input
                            className="w-full bg-[#12141C] border border-white/10 rounded-xl py-2 pl-10 pr-4 text-sm text-white focus:outline-none focus:border-blue-500/50"
                            placeholder={`Search ${mode}...`}
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                        />
                    </div>

                    <div className="flex-1 bg-[#12141C] rounded-2xl border border-white/10 overflow-hidden flex flex-col shadow-2xl min-h-0">
                        <div className="grid grid-cols-12 px-6 py-3 bg-white/5 font-medium text-sm text-gray-400 border-b border-white/5 flex-shrink-0">
                            <div className="col-span-2">PID</div>
                            <div className="col-span-8">Name / ID</div>
                        </div>
                        <div className="flex-1 overflow-auto custom-scrollbar">
                            {/* Replaced ScrollArea with native div using custom-scrollbar class for better control if ScrollArea fails */}
                            {loading ? (
                                <div className="flex flex-col items-center justify-center p-20 text-gray-500">
                                    <Server className="w-10 h-10 mb-4 opacity-50 animate-pulse" />
                                    <p>Scanning device...</p>
                                </div>
                            ) : (
                                <div className="divide-y divide-white/5">
                                    {filteredItems.map((p, i) => (
                                        <div key={i} className="grid grid-cols-12 px-6 py-3 hover:bg-white/[0.02] transition-colors items-center text-sm">
                                            <div className="col-span-2 font-mono text-blue-400 text-xs">{p.pid}</div>
                                            <div className="col-span-8 flex flex-col justify-center">
                                                <span className="text-gray-200 font-medium truncate pr-4">{p.name}</span>
                                                {p.identifier && <span className="text-gray-600 text-xs truncate pr-4">{p.identifier}</span>}
                                            </div>

                                        </div>
                                    ))}
                                </div>
                            )}
                            {!loading && filteredItems.length === 0 && (
                                <div className="p-12 text-center text-gray-500">
                                    No items found.
                                </div>
                            )}
                        </div>
                    </div>
                </Tabs>
            </main>
        </div>
    );
}

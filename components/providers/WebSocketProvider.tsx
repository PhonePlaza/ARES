"use client";

import React, { createContext, useContext, useEffect, useRef, useState } from "react";

interface WebSocketContextType {
    isConnected: boolean;
    logs: string[];
    addLog: (log: string) => void;
    sendMessage: (msg: string) => void;
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined);

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
    const [isConnected, setIsConnected] = useState(false);
    const [logs, setLogs] = useState<string[]>([]);
    const wsRef = useRef<WebSocket | null>(null);

    useEffect(() => {
        const connect = () => {
            // Avoid multiple connections
            if (wsRef.current?.readyState === WebSocket.OPEN) return;

            try {
                const ws = new WebSocket("ws://localhost:8000/ws/logs");

                ws.onopen = () => {
                    console.log("[WS] Connected");
                    setIsConnected(true);
                    setLogs(prev => [...prev, "[SYSTEM] Connected to Frida Backend"]);
                };

                ws.onmessage = (event) => {
                    setLogs(prev => [...prev, event.data]);
                };

                ws.onclose = () => {
                    console.log("[WS] Disconnected");
                    setIsConnected(false);
                    setLogs(prev => [...prev, "[SYSTEM] Disconnected (Backend might be offline)"]);
                    // Optional: Reconnect logic could go here
                };

                ws.onerror = (err) => {
                    console.error("[WS] Error:", err);
                };

                wsRef.current = ws;
            } catch (e) {
                console.error("[WS] Connection failed:", e);
            }
        };

        connect();

        return () => {
            // We usually don't want to close it on unmount of Provider (which is App root), 
            // but good practice for cleanup if strict mode de-mounts.
            if (wsRef.current) {
                wsRef.current.close();
            }
        };
    }, []);

    const sendMessage = (msg: string) => {
        if (wsRef.current && isConnected) {
            wsRef.current.send(msg);
        }
    };

    const addLog = (log: string) => {
        setLogs(prev => [...prev, log]);
    };

    return (
        <WebSocketContext.Provider value={{ isConnected, logs, addLog, sendMessage }}>
            {children}
        </WebSocketContext.Provider>
    );
}

export function useWebSocket() {
    const context = useContext(WebSocketContext);
    if (context === undefined) {
        throw new Error("useWebSocket must be used within a WebSocketProvider");
    }
    return context;
}

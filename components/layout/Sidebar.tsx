import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Shield, LayoutDashboard, Terminal, FileText, Activity, ClipboardList } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

export function Sidebar() {
    return (
        <div className="w-64 flex-col hidden md:flex h-screen bg-[#0B0E14] border-r border-white/5 text-white">
            {/* Header */}
            <div className="p-6">
                <div className="flex items-center gap-3 mb-8">
                    <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-blue-600 to-purple-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
                        <Shield className="h-6 w-6 text-white" />
                    </div>
                    <div>
                        <h2 className="font-bold text-lg tracking-tight">Frida Agent</h2>
                        <span className="text-xs text-blue-400 font-medium">v1.0.0 Beta</span>
                    </div>
                </div>

                <Link href="/analysis" passHref>
                    <Button className="w-full bg-blue-600 hover:bg-blue-500 shadow-md shadow-blue-900/20 mb-6">
                        + New Analysis
                    </Button>
                </Link>

                {/* Navigation */}
                <ScrollArea className="flex-1 -mx-2 px-2">
                    <div className="space-y-1">
                        <p className="text-xs font-semibold text-gray-500 px-4 mb-2 uppercase tracking-wider">Main</p>
                        <NavItem icon={LayoutDashboard} label="Dashboard" href="/" />
                        <NavItem icon={Activity} label="Live Agent" href="/agent" />
                        <NavItem icon={Terminal} label="Script Editor" href="/editor" />
                    </div>

                    <div className="space-y-1 mt-8">
                        <p className="text-xs font-semibold text-gray-500 px-4 mb-2 uppercase tracking-wider">Reports</p>
                        <NavItem icon={ClipboardList} label="Report History" href="/reports" />
                    </div>
                </ScrollArea>
            </div>

            {/* Footer */}
            <div className="p-6 mt-auto border-t border-white/5">
                <div className="glass-panel p-4 rounded-xl relative overflow-hidden group hover:border-blue-500/30 transition-colors">
                    <div className="absolute inset-0 bg-blue-500/10 opacity-0 group-hover:opacity-100 transition-opacity" />
                    <h4 className="font-semibold text-sm mb-1 relative z-10">Agent Status</h4>
                    <p className="text-xs text-gray-400 relative z-10">System is ready for injection.</p>
                </div>
            </div>
        </div>
    );
}


function NavItem({ icon: Icon, label, href, active }: { icon: any, label: string, href: string, active?: boolean }) {
    // If active prop is passed explicitly, use it, otherwise check pathname
    // But for simplicity in this replacement, we'll let parent control or check inside
    return (
        <Link href={href} passHref className="w-full block">
            <Button
                variant="ghost"
                className={`w-full justify-start gap-3 h-11 rounded-lg ${active ? "bg-white/5 text-white font-medium border border-white/5" : "text-gray-400 hover:text-white hover:bg-white/5"}`}
            >
                <Icon className={`h-4 w-4 ${active ? "text-blue-400" : "text-gray-500 group-hover:text-gray-400"}`} />
                {label}
            </Button>
        </Link>
    )
}

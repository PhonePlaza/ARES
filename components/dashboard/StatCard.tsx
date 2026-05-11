import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LucideIcon } from "lucide-react";

interface StatCardProps {
    title: string;
    value: string | number;
    icon: LucideIcon;
    trend?: string;
    trendUp?: boolean;
}

export function StatCard({ title, value, icon: Icon, trend, trendUp }: StatCardProps) {
    return (
        <Card className="glass-panel border-white/5 bg-white/5 text-white backdrop-blur-md">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-gray-400">{title}</CardTitle>
                <Icon className="h-4 w-4 text-blue-400" />
            </CardHeader>
            <CardContent>
                <div className="text-2xl font-bold bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
                    {value}
                </div>
                {trend && (
                    <p className={`text-xs ${trendUp ? "text-emerald-400" : "text-rose-400"} mt-1`}>
                        {trend}
                    </p>
                )}
            </CardContent>
        </Card>
    );
}

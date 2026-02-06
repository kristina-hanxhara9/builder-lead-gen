"use client";

import { useEffect, useState } from "react";
import {
  BarChart3,
  FileText,
  Mail,
  QrCode,
  TrendingUp,
  Users,
} from "lucide-react";
import { getDashboardStats, getPipeline } from "@/lib/api";
import type { DashboardStats, PipelineResponse } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [pipeline, setPipeline] = useState<PipelineResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [s, p] = await Promise.all([getDashboardStats(), getPipeline()]);
        setStats(s);
        setPipeline(p);
      } catch (e) {
        console.error("Failed to load dashboard:", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-navy-900 border-t-transparent rounded-full" />
      </div>
    );
  }

  const statCards = [
    {
      label: "New Leads Today",
      value: stats?.new_leads_today ?? 0,
      icon: Users,
      color: "text-blue-600 bg-blue-50",
    },
    {
      label: "Total Leads",
      value: stats?.total_leads ?? 0,
      icon: BarChart3,
      color: "text-navy-900 bg-navy-50",
    },
    {
      label: "Letters Pending",
      value: stats?.letters_pending ?? 0,
      icon: FileText,
      color: "text-yellow-600 bg-yellow-50",
    },
    {
      label: "Letters Sent",
      value: stats?.letters_sent ?? 0,
      icon: Mail,
      color: "text-green-600 bg-green-50",
    },
    {
      label: "QR Scans",
      value: stats?.qr_scans_total ?? 0,
      icon: QrCode,
      color: "text-purple-600 bg-purple-50",
    },
    {
      label: "Conversion Rate",
      value: `${stats?.conversion_rate ?? 0}%`,
      icon: TrendingUp,
      color: "text-gold-600 bg-gold-50",
    },
  ];

  return (
    <div className="space-y-8">
      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {statCards.map((card) => (
          <div
            key={card.label}
            className="bg-white rounded-xl border border-gray-200 p-6 hover:shadow-md transition-shadow"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">{card.label}</p>
                <p className="text-3xl font-bold text-navy-900 mt-1">
                  {card.value}
                </p>
              </div>
              <div className={`p-3 rounded-lg ${card.color}`}>
                <card.icon className="w-6 h-6" />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Pipeline + Value */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Pipeline Funnel */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-navy-900 mb-4">
            Lead Pipeline
          </h3>
          <div className="space-y-3">
            {pipeline?.stages.map((stage) => {
              const maxCount = Math.max(
                ...( pipeline.stages.map((s) => s.count) || [1])
              );
              const width = maxCount > 0 ? (stage.count / maxCount) * 100 : 0;
              return (
                <div key={stage.stage} className="flex items-center gap-4">
                  <span className="text-sm text-gray-600 w-24 capitalize">
                    {stage.stage}
                  </span>
                  <div className="flex-1 bg-gray-100 rounded-full h-8 overflow-hidden">
                    <div
                      className="bg-navy-900 h-full rounded-full flex items-center justify-end px-3 transition-all"
                      style={{ width: `${Math.max(width, 5)}%` }}
                    >
                      <span className="text-xs text-white font-medium">
                        {stage.count}
                      </span>
                    </div>
                  </div>
                  <span className="text-sm text-gray-500 w-24 text-right">
                    {formatCurrency(stage.value)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Key Metrics */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-navy-900 mb-4">
            Key Metrics
          </h3>
          <div className="space-y-6">
            <div>
              <p className="text-sm text-gray-500">Pipeline Value</p>
              <p className="text-3xl font-bold text-navy-900">
                {formatCurrency(stats?.pipeline_value ?? 0)}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Avg Lead Score</p>
              <p className="text-3xl font-bold text-navy-900">
                {stats?.avg_lead_score ?? 0}
                <span className="text-lg text-gray-400">/100</span>
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Conversion Rate</p>
              <p className="text-3xl font-bold text-green-600">
                {stats?.conversion_rate ?? 0}%
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

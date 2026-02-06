"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Building,
  Download,
  FileText,
  MapPin,
  Star,
  Thermometer,
} from "lucide-react";
import { getLead, getLetters, updateLeadStatus } from "@/lib/api";
import type { Lead, Letter } from "@/lib/api";
import { cn, formatCurrency, formatDate, getScoreColor, getStatusColor } from "@/lib/utils";

export default function LeadDetailPage() {
  const params = useParams();
  const router = useRouter();
  const [lead, setLead] = useState<Lead | null>(null);
  const [letters, setLetters] = useState<Letter[]>([]);
  const [loading, setLoading] = useState(true);

  const leadId = params.id as string;

  useEffect(() => {
    async function load() {
      try {
        const l = await getLead(leadId);
        setLead(l);
        const letterData = await getLetters();
        setLetters(letterData.letters.filter((lt) => lt.lead_id === leadId));
      } catch (e) {
        console.error("Failed to load lead:", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [leadId]);

  async function handleStatusChange(newStatus: string) {
    if (!lead) return;
    try {
      const updated = await updateLeadStatus(lead.id, newStatus);
      setLead(updated);
    } catch (e) {
      console.error("Failed to update status:", e);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-navy-900 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!lead) {
    return <div className="text-center text-gray-500 py-12">Lead not found</div>;
  }

  const unified = lead.unified_data || {};
  const breakdown = lead.score_breakdown || {};

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Back button */}
      <button
        onClick={() => router.push("/dashboard/leads")}
        className="flex items-center gap-2 text-sm text-gray-500 hover:text-navy-900 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" /> Back to leads
      </button>

      {/* Header */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-xl font-bold text-navy-900">{lead.address}</h2>
            <p className="text-gray-500 mt-1">{lead.postcode}</p>
            <p className="text-sm text-gray-600 mt-2">{lead.work_description}</p>
          </div>
          <div className="text-right">
            <div
              className={cn(
                "inline-flex px-4 py-2 rounded-full text-2xl font-bold",
                getScoreColor(lead.lead_score)
              )}
            >
              {lead.lead_score}
            </div>
            <p className="text-xs text-gray-400 mt-1">Lead Score</p>
          </div>
        </div>

        {/* Status actions */}
        <div className="flex items-center gap-3 mt-6 pt-4 border-t border-gray-100">
          <span className="text-sm text-gray-500">Status:</span>
          {["new", "contacted", "quoted", "won", "lost"].map((s) => (
            <button
              key={s}
              onClick={() => handleStatusChange(s)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-sm capitalize transition-colors",
                lead.status === s
                  ? getStatusColor(s) + " font-semibold"
                  : "bg-gray-50 text-gray-400 hover:bg-gray-100"
              )}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Score Breakdown + Property Info */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Score Breakdown */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-navy-900 mb-4 flex items-center gap-2">
            <Star className="w-5 h-5 text-gold" /> Score Breakdown
          </h3>
          <div className="space-y-4">
            {Object.entries(breakdown)
              .filter(([k]) => k !== "total")
              .map(([key, val]: [string, any]) => (
                <div key={key}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-600 capitalize">
                      {key.replace("_", " ")}
                    </span>
                    <span className="font-medium text-navy-900">
                      {val.score}/{val.max}
                    </span>
                  </div>
                  <div className="w-full bg-gray-100 rounded-full h-2">
                    <div
                      className="bg-navy-900 h-2 rounded-full transition-all"
                      style={{
                        width: `${(val.score / val.max) * 100}%`,
                      }}
                    />
                  </div>
                </div>
              ))}
          </div>
        </div>

        {/* Property Details */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-navy-900 mb-4 flex items-center gap-2">
            <Building className="w-5 h-5 text-gold" /> Property Details
          </h3>
          <dl className="space-y-3">
            {[
              ["Property Type", unified.property_type],
              ["Construction Age", unified.construction_age],
              ["Floor Area", unified.total_floor_area_m2 ? `${unified.total_floor_area_m2} m²` : null],
              ["EPC Rating", unified.epc_rating],
              ["Est. Value", lead.property_value_estimate ? formatCurrency(lead.property_value_estimate) : null],
              ["Distance", lead.distance_km ? `${lead.distance_km} km` : null],
              ["Planning Ref", unified.planning_reference],
              ["Authority", unified.local_authority],
            ]
              .filter(([_, v]) => v)
              .map(([label, value]) => (
                <div key={label as string} className="flex justify-between">
                  <dt className="text-sm text-gray-500">{label}</dt>
                  <dd className="text-sm font-medium text-navy-900">{value}</dd>
                </div>
              ))}
          </dl>
        </div>
      </div>

      {/* Letters */}
      {letters.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-navy-900 mb-4 flex items-center gap-2">
            <FileText className="w-5 h-5 text-gold" /> Letters
          </h3>
          <div className="space-y-4">
            {letters.map((letter) => (
              <div
                key={letter.id}
                className="border border-gray-100 rounded-lg p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <span
                    className={cn(
                      "px-2.5 py-1 rounded-full text-xs font-medium capitalize",
                      getStatusColor(letter.status)
                    )}
                  >
                    {letter.status}
                  </span>
                  <span className="text-sm text-gray-400">
                    {formatDate(letter.created_at)}
                  </span>
                </div>
                {letter.content && (
                  <p className="text-sm text-gray-600 line-clamp-4 whitespace-pre-wrap">
                    {letter.content.slice(0, 300)}...
                  </p>
                )}
                <div className="flex items-center justify-between mt-3">
                  <div className="flex items-center gap-4 text-xs text-gray-400">
                    <span>QR Scans: {letter.qr_scan_count}</span>
                    <span>Cost: £{letter.generation_cost_gbp.toFixed(3)}</span>
                  </div>
                  <a
                    href={`/api/letters/${letter.id}/download`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-200 text-gray-600 rounded-lg text-xs hover:bg-gray-50 transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" /> Download PDF
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

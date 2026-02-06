"use client";

import { useEffect, useState } from "react";
import { Check, Mail, Send } from "lucide-react";
import { approveLetter, getLetters, sendLetter } from "@/lib/api";
import type { Letter, LetterListResponse } from "@/lib/api";
import { cn, formatDate, getStatusColor } from "@/lib/utils";

export default function LettersPage() {
  const [data, setData] = useState<LetterListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");

  async function load() {
    setLoading(true);
    try {
      const result = await getLetters(statusFilter || undefined);
      setData(result);
    } catch (e) {
      console.error("Failed to load letters:", e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [statusFilter]);

  async function handleApprove(letterId: string) {
    try {
      await approveLetter(letterId);
      load();
    } catch (e) {
      console.error("Failed to approve:", e);
    }
  }

  async function handleSend(letterId: string) {
    try {
      await sendLetter(letterId);
      load();
    } catch (e) {
      console.error("Failed to send:", e);
    }
  }

  const statuses = ["", "draft", "approved", "queued", "posted", "delivered"];

  return (
    <div className="space-y-6">
      {/* Filters */}
      <div className="flex items-center gap-2">
        {statuses.map((s) => (
          <button
            key={s || "all"}
            onClick={() => setStatusFilter(s)}
            className={cn(
              "px-3 py-1.5 rounded-lg text-sm capitalize transition-colors",
              statusFilter === s
                ? "bg-navy-900 text-white"
                : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"
            )}
          >
            {s || "All"}
          </button>
        ))}
        <span className="ml-auto text-sm text-gray-500">
          {data?.total ?? 0} letters
        </span>
      </div>

      {/* Letters Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {loading ? (
          <div className="col-span-2 text-center py-12 text-gray-400">
            Loading...
          </div>
        ) : data?.letters.length === 0 ? (
          <div className="col-span-2 text-center py-12 text-gray-400">
            No letters found
          </div>
        ) : (
          data?.letters.map((letter) => (
            <div
              key={letter.id}
              className="bg-white rounded-xl border border-gray-200 p-6 hover:shadow-md transition-shadow"
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-4">
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

              {/* Content preview */}
              {letter.content && (
                <p className="text-sm text-gray-600 line-clamp-6 whitespace-pre-wrap mb-4">
                  {letter.content.slice(0, 400)}...
                </p>
              )}

              {/* Metrics */}
              <div className="flex items-center gap-4 text-xs text-gray-400 mb-4">
                <span>QR Scans: {letter.qr_scan_count}</span>
                <span>Gen Cost: £{letter.generation_cost_gbp.toFixed(3)}</span>
                {letter.print_cost_gbp > 0 && (
                  <span>Print: £{letter.print_cost_gbp.toFixed(2)}</span>
                )}
              </div>

              {/* Actions */}
              <div className="flex gap-2 pt-3 border-t border-gray-100">
                {letter.status === "draft" && (
                  <button
                    onClick={() => handleApprove(letter.id)}
                    className="flex items-center gap-1.5 px-4 py-2 bg-green-50 text-green-700 rounded-lg text-sm hover:bg-green-100 transition-colors"
                  >
                    <Check className="w-4 h-4" /> Approve
                  </button>
                )}
                {(letter.status === "approved" || letter.status === "draft") && (
                  <button
                    onClick={() => handleSend(letter.id)}
                    className="flex items-center gap-1.5 px-4 py-2 bg-navy-900 text-white rounded-lg text-sm hover:bg-navy-700 transition-colors"
                  >
                    <Send className="w-4 h-4" /> Send via Royal Mail
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

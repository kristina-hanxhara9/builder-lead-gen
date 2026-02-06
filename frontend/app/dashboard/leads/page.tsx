"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronRight, Filter, Search } from "lucide-react";
import { getLeads } from "@/lib/api";
import type { Lead, LeadListResponse } from "@/lib/api";
import { cn, formatCurrency, formatDate, getScoreColor, getStatusColor } from "@/lib/utils";

export default function LeadsPage() {
  const [data, setData] = useState<LeadListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const result = await getLeads({
          page,
          per_page: 20,
          status: statusFilter || undefined,
        });
        setData(result);
      } catch (e) {
        console.error("Failed to load leads:", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [page, statusFilter]);

  const statuses = ["", "new", "contacted", "quoted", "won", "lost"];

  return (
    <div className="space-y-6">
      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-gray-400" />
          <span className="text-sm text-gray-500">Status:</span>
          {statuses.map((s) => (
            <button
              key={s || "all"}
              onClick={() => {
                setStatusFilter(s);
                setPage(1);
              }}
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
        </div>
        <div className="ml-auto text-sm text-gray-500">
          {data?.total ?? 0} leads total
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">
                Address
              </th>
              <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">
                Work Type
              </th>
              <th className="text-center px-6 py-3 text-xs font-medium text-gray-500 uppercase">
                Score
              </th>
              <th className="text-center px-6 py-3 text-xs font-medium text-gray-500 uppercase">
                Status
              </th>
              <th className="text-right px-6 py-3 text-xs font-medium text-gray-500 uppercase">
                Value
              </th>
              <th className="text-right px-6 py-3 text-xs font-medium text-gray-500 uppercase">
                Date
              </th>
              <th className="px-6 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading ? (
              <tr>
                <td colSpan={7} className="px-6 py-12 text-center text-gray-400">
                  Loading...
                </td>
              </tr>
            ) : data?.leads.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-6 py-12 text-center text-gray-400">
                  No leads found
                </td>
              </tr>
            ) : (
              data?.leads.map((lead) => (
                <tr key={lead.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4">
                    <div className="text-sm font-medium text-navy-900">
                      {lead.address.split(",")[0]}
                    </div>
                    <div className="text-xs text-gray-500">{lead.postcode}</div>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600">
                    {lead.work_type?.replace("_", " ") || "—"}
                  </td>
                  <td className="px-6 py-4 text-center">
                    <span
                      className={cn(
                        "inline-flex px-2.5 py-1 rounded-full text-sm font-semibold",
                        getScoreColor(lead.lead_score)
                      )}
                    >
                      {lead.lead_score}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-center">
                    <span
                      className={cn(
                        "inline-flex px-2.5 py-1 rounded-full text-xs font-medium capitalize",
                        getStatusColor(lead.status)
                      )}
                    >
                      {lead.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right text-sm text-gray-600">
                    {lead.property_value_estimate
                      ? formatCurrency(lead.property_value_estimate)
                      : "—"}
                  </td>
                  <td className="px-6 py-4 text-right text-sm text-gray-500">
                    {formatDate(lead.created_at)}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <Link
                      href={`/dashboard/leads/${lead.id}`}
                      className="text-navy-900 hover:text-gold transition-colors"
                    >
                      <ChevronRight className="w-5 h-5" />
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>

        {/* Pagination */}
        {data && data.total > data.per_page && (
          <div className="flex items-center justify-between px-6 py-3 border-t border-gray-200 bg-gray-50">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="text-sm text-navy-900 disabled:text-gray-300"
            >
              Previous
            </button>
            <span className="text-sm text-gray-500">
              Page {page} of {Math.ceil(data.total / data.per_page)}
            </span>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={page >= Math.ceil(data.total / data.per_page)}
              className="text-sm text-navy-900 disabled:text-gray-300"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

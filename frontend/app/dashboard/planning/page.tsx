"use client";

import { useEffect, useState } from "react";
import { MapPin, RefreshCw, Plus, Play, Loader2, CheckCircle, XCircle } from "lucide-react";
import { getPlanningApps, triggerSync, addPlanningApp, processApplication, getAvailableCouncils } from "@/lib/api";
import type { PlanningApp } from "@/lib/api";
import { formatDate } from "@/lib/utils";

export default function PlanningPage() {
  const [apps, setApps] = useState<PlanningApp[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [processing, setProcessing] = useState<string | null>(null);
  const [processResult, setProcessResult] = useState<Record<string, any> | null>(null);

  // Add form state
  const [formRef, setFormRef] = useState("");
  const [formAddress, setFormAddress] = useState("");
  const [formPostcode, setFormPostcode] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formDetailUrl, setFormDetailUrl] = useState("");
  const [formCouncil, setFormCouncil] = useState("");
  const [councils, setCouncils] = useState<string[]>([]);

  async function load() {
    setLoading(true);
    try {
      const result = await getPlanningApps();
      setApps(result);
    } catch (e) {
      console.error("Failed to load planning apps:", e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    getAvailableCouncils()
      .then((res) => setCouncils(res.councils))
      .catch(() => setCouncils(["Lambeth", "Wandsworth", "Richmond"]));
  }, []);

  async function handleSync() {
    setSyncing(true);
    setSyncResult(null);
    try {
      const result = await triggerSync(7);
      setSyncResult(
        `Sync complete: ${result.fetched ?? 0} fetched, ${result.new ?? 0} new`
      );
      await load();
    } catch (e: any) {
      setSyncResult(`Sync failed: ${e.message}`);
    } finally {
      setSyncing(false);
    }
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    try {
      await addPlanningApp({
        reference: formRef,
        address: formAddress,
        postcode: formPostcode,
        description: formDescription,
        detail_url: formDetailUrl,
        local_authority: formCouncil,
      });
      setShowAddForm(false);
      setFormRef("");
      setFormAddress("");
      setFormPostcode("");
      setFormDescription("");
      setFormDetailUrl("");
      setFormCouncil("");
      await load();
    } catch (e) {
      console.error("Failed to add application:", e);
    }
  }

  async function handleProcess(appId: string) {
    setProcessing(appId);
    setProcessResult(null);
    try {
      const result = await processApplication(appId);
      setProcessResult(result);
      await load();
    } catch (e: any) {
      setProcessResult({ status: "error", message: e.message });
    } finally {
      setProcessing(null);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <p className="text-sm text-gray-500">
            Planning applications in SW London — sync from councils or add manually
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg text-sm hover:bg-gray-50 transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add Manually
          </button>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex items-center gap-2 px-4 py-2 bg-navy-900 text-white rounded-lg text-sm hover:bg-navy-700 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${syncing ? "animate-spin" : ""}`} />
            {syncing ? "Syncing..." : "Sync from Councils"}
          </button>
        </div>
      </div>

      {/* Sync result banner */}
      {syncResult && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-sm text-blue-800">
          {syncResult}
        </div>
      )}

      {/* Process result banner */}
      {processResult && (
        <div
          className={`rounded-lg px-4 py-3 text-sm border ${
            processResult.status === "complete"
              ? "bg-green-50 border-green-200 text-green-800"
              : "bg-red-50 border-red-200 text-red-800"
          }`}
        >
          {processResult.status === "complete" ? (
            <div className="space-y-1">
              <div className="flex items-center gap-2 font-medium">
                <CheckCircle className="w-4 h-4" />
                Pipeline complete for {processResult.reference}
              </div>
              <div className="ml-6 text-xs space-y-0.5">
                <p>Extraction: {(processResult.extraction_confidence * 100).toFixed(0)}% confidence, {processResult.fields_extracted} fields</p>
                <p>Lead Score: {processResult.lead_score}/100</p>
                <p>Letter: {processResult.letter_generated ? `Generated (${processResult.pdf_size_kb} KB PDF)` : "Not generated"}</p>
                <p>Cost: £{processResult.total_cost_gbp?.toFixed(4)}</p>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <XCircle className="w-4 h-4" />
              Processing failed: {processResult.message || "Unknown error"}
            </div>
          )}
        </div>
      )}

      {/* Add form */}
      {showAddForm && (
        <form
          onSubmit={handleAdd}
          className="bg-white rounded-xl border border-gray-200 p-6 space-y-4"
        >
          <h3 className="font-semibold text-navy-900">Add Planning Application</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Reference *</label>
              <input
                type="text"
                value={formRef}
                onChange={(e) => setFormRef(e.target.value)}
                required
                placeholder="e.g. 24/00756/FUL"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-navy-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Postcode *</label>
              <input
                type="text"
                value={formPostcode}
                onChange={(e) => setFormPostcode(e.target.value)}
                required
                placeholder="e.g. SW2 2RP"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-navy-500 focus:border-transparent"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-xs text-gray-500 mb-1">Address *</label>
              <input
                type="text"
                value={formAddress}
                onChange={(e) => setFormAddress(e.target.value)}
                required
                placeholder="e.g. 76 Upper Tulse Hill, London"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-navy-500 focus:border-transparent"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-xs text-gray-500 mb-1">Description</label>
              <input
                type="text"
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                placeholder="e.g. Erection of a first floor rear extension"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-navy-500 focus:border-transparent"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-xs text-gray-500 mb-1">
                Planning Portal Detail URL
                <span className="text-gray-400 ml-1">(enables auto PDF discovery)</span>
              </label>
              <input
                type="url"
                value={formDetailUrl}
                onChange={(e) => setFormDetailUrl(e.target.value)}
                placeholder="e.g. https://planning.lambeth.gov.uk/online-applications/applicationDetails.do?..."
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-navy-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Council</label>
              <select
                value={formCouncil}
                onChange={(e) => setFormCouncil(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-navy-500 focus:border-transparent"
              >
                <option value="">Select...</option>
                {councils.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex gap-3">
            <button
              type="submit"
              className="px-4 py-2 bg-navy-900 text-white rounded-lg text-sm hover:bg-navy-700 transition-colors"
            >
              Add Application
            </button>
            <button
              type="button"
              onClick={() => setShowAddForm(false)}
              className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg text-sm hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Applications list */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">
                Reference
              </th>
              <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">
                Address
              </th>
              <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">
                Description
              </th>
              <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">
                Council
              </th>
              <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">
                Status
              </th>
              <th className="text-right px-6 py-3 text-xs font-medium text-gray-500 uppercase">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading ? (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-gray-400">
                  <Loader2 className="w-6 h-6 mx-auto mb-2 animate-spin" />
                  Loading...
                </td>
              </tr>
            ) : apps.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-gray-400">
                  <MapPin className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                  <p>No planning applications yet.</p>
                  <p className="text-xs mt-1">
                    Click "Sync from Councils" or "Add Manually" to get started.
                  </p>
                </td>
              </tr>
            ) : (
              apps.map((app) => (
                <tr key={app.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4 text-sm font-mono text-navy-900">
                    {app.reference}
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-sm text-gray-900">
                      {app.address.split(",")[0]}
                    </div>
                    <div className="text-xs text-gray-500">{app.postcode}</div>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600 max-w-xs truncate">
                    {app.description || "—"}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600">
                    {app.local_authority || "—"}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600">
                    {app.decision || app.status || "Pending"}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button
                      onClick={() => handleProcess(app.id)}
                      disabled={processing === app.id}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-green-600 text-white rounded-lg text-xs font-medium hover:bg-green-700 disabled:opacity-50 transition-colors"
                    >
                      {processing === app.id ? (
                        <>
                          <Loader2 className="w-3 h-3 animate-spin" />
                          Processing...
                        </>
                      ) : (
                        <>
                          <Play className="w-3 h-3" />
                          Run Pipeline
                        </>
                      )}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

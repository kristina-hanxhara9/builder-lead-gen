"use client";

import { useEffect, useState } from "react";
import {
  Bell,
  Building,
  Check,
  Hammer,
  Loader2,
  MapPin,
  Plus,
  Save,
  Target,
  X,
} from "lucide-react";
import { getSettings, updateSettings } from "@/lib/api";
import type { AppSettings, SettingsUpdateRequest } from "@/lib/api";

// All known service type codes with friendly labels
const SERVICE_TYPE_LABELS: Record<string, string> = {
  EXTENSION: "Extensions",
  CONVERSION_LOFT: "Loft Conversions",
  KITCHEN: "Kitchen Extensions",
  CONVERSION_GARAGE: "Garage Conversions",
  BATHROOM: "Bathrooms",
  CONVERSION_BASEMENT: "Basement Conversions",
  NEW_BUILD: "New Builds",
  RENOVATION: "Renovations",
  SOLAR_PV: "Solar PV",
  HEAT_PUMP: "Heat Pumps",
  GENERAL_RENOVATION: "General Renovation",
};

// Known councils with portal support
const ALL_COUNCILS = [
  "wandsworth",
  "lambeth",
  "richmond",
  "merton",
  "kingston",
  "croydon",
  "sutton",
  "southwark",
  "lewisham",
];

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveResult, setSaveResult] = useState<{
    ok: boolean;
    msg: string;
  } | null>(null);

  // ── Editable state ──
  const [company, setCompany] = useState({
    name: "",
    owner_name: "",
    phone: "",
    email: "",
    website: "",
    office_address: "",
    company_registration: "",
    vat_number: "",
  });
  const [services, setServices] = useState<{
    primary: string[];
    secondary: string[];
    exclude: string[];
  }>({ primary: [], secondary: [], exclude: [] });
  const [geo, setGeo] = useState<{
    districts: string[];
    max_distance_km: number;
    borough_councils: string[];
  }>({ districts: [], max_distance_km: 8, borough_councils: [] });
  const [scoring, setScoring] = useState({
    weights: { geography: 30, property_value: 25, work_type: 30, timing: 15 } as Record<string, number>,
    minimum_score: 65,
    auto_send_threshold: 85,
  });

  // Temp inputs for adding items
  const [newDistrict, setNewDistrict] = useState("");
  const [newCouncil, setNewCouncil] = useState("");

  useEffect(() => {
    loadSettings();
  }, []);

  async function loadSettings() {
    setLoading(true);
    try {
      const data = await getSettings();
      setSettings(data);
      setCompany({
        name: data.company.name,
        owner_name: data.company.owner_name,
        phone: data.company.phone,
        email: data.company.email,
        website: data.company.website,
        office_address: data.company.office_address,
        company_registration: data.company.company_registration,
        vat_number: data.company.vat_number,
      });
      setServices(data.services);
      setGeo(data.geographic_area);
      setScoring(data.lead_scoring);
    } catch (e) {
      console.error("Failed to load settings:", e);
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setSaveResult(null);
    try {
      const payload: SettingsUpdateRequest = {
        company,
        services,
        geographic_area: geo,
        lead_scoring: scoring,
      };
      await updateSettings(payload);
      setSaveResult({ ok: true, msg: "Settings saved successfully!" });
      setTimeout(() => setSaveResult(null), 4000);
    } catch (e: any) {
      setSaveResult({
        ok: false,
        msg: e.message || "Failed to save settings",
      });
    } finally {
      setSaving(false);
    }
  }

  // ── Service tier helpers ──
  function moveService(code: string, from: keyof typeof services, to: keyof typeof services) {
    setServices((prev) => ({
      ...prev,
      [from]: prev[from].filter((s) => s !== code),
      [to]: [...prev[to].filter((s) => s !== code), code],
    }));
  }

  // Get unassigned service types
  const assignedServices = [
    ...services.primary,
    ...services.secondary,
    ...services.exclude,
  ];
  const unassignedServices = Object.keys(SERVICE_TYPE_LABELS).filter(
    (s) => !assignedServices.includes(s)
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Save banner */}
      {saveResult && (
        <div
          className={`rounded-lg px-4 py-3 text-sm border flex items-center gap-2 ${
            saveResult.ok
              ? "bg-green-50 border-green-200 text-green-800"
              : "bg-red-50 border-red-200 text-red-800"
          }`}
        >
          {saveResult.ok ? (
            <Check className="w-4 h-4" />
          ) : (
            <X className="w-4 h-4" />
          )}
          {saveResult.msg}
        </div>
      )}

      {/* ═══ Company Details ═══ */}
      <section className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-navy-900 mb-4 flex items-center gap-2">
          <Building className="w-5 h-5 text-gold" /> Company Details
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {([
            { label: "Company Name", key: "name" as const },
            { label: "Owner Name", key: "owner_name" as const },
            { label: "Phone", key: "phone" as const },
            { label: "Email", key: "email" as const },
            { label: "Website", key: "website" as const },
            { label: "Company Reg", key: "company_registration" as const },
            { label: "VAT Number", key: "vat_number" as const },
          ]).map(({ label, key }) => (
            <div key={key}>
              <label className="block text-xs text-gray-500 mb-1">
                {label}
              </label>
              <input
                type="text"
                value={company[key]}
                onChange={(e) =>
                  setCompany({ ...company, [key]: e.target.value })
                }
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-navy-500 focus:border-transparent"
              />
            </div>
          ))}
          <div className="md:col-span-2">
            <label className="block text-xs text-gray-500 mb-1">
              Office Address
            </label>
            <input
              type="text"
              value={company.office_address}
              onChange={(e) =>
                setCompany({ ...company, office_address: e.target.value })
              }
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-navy-500 focus:border-transparent"
            />
          </div>
        </div>
      </section>

      {/* ═══ Services Offered ═══ */}
      <section className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-navy-900 mb-4 flex items-center gap-2">
          <Hammer className="w-5 h-5 text-gold" /> Services Offered
        </h3>
        <p className="text-xs text-gray-500 mb-4">
          Move services between tiers to control how leads are scored.{" "}
          <strong>Primary</strong> = full score,{" "}
          <strong>Secondary</strong> = partial score,{" "}
          <strong>Excluded</strong> = skip these leads.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Primary */}
          <div className="border border-green-200 rounded-lg p-4 bg-green-50/50">
            <h4 className="text-sm font-semibold text-green-800 mb-3">
              Primary Services
              <span className="text-xs font-normal text-green-600 ml-1">
                (full score)
              </span>
            </h4>
            <div className="space-y-2">
              {services.primary.map((code) => (
                <div
                  key={code}
                  className="flex items-center justify-between bg-white rounded-lg px-3 py-2 border border-green-200"
                >
                  <span className="text-sm">
                    {SERVICE_TYPE_LABELS[code] || code}
                  </span>
                  <div className="flex gap-1">
                    <button
                      onClick={() => moveService(code, "primary", "secondary")}
                      className="text-xs text-gray-400 hover:text-orange-600 px-1"
                      title="Move to Secondary"
                    >
                      2nd
                    </button>
                    <button
                      onClick={() => moveService(code, "primary", "exclude")}
                      className="text-xs text-gray-400 hover:text-red-600 px-1"
                      title="Exclude"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Secondary */}
          <div className="border border-orange-200 rounded-lg p-4 bg-orange-50/50">
            <h4 className="text-sm font-semibold text-orange-800 mb-3">
              Secondary Services
              <span className="text-xs font-normal text-orange-600 ml-1">
                (partial score)
              </span>
            </h4>
            <div className="space-y-2">
              {services.secondary.map((code) => (
                <div
                  key={code}
                  className="flex items-center justify-between bg-white rounded-lg px-3 py-2 border border-orange-200"
                >
                  <span className="text-sm">
                    {SERVICE_TYPE_LABELS[code] || code}
                  </span>
                  <div className="flex gap-1">
                    <button
                      onClick={() => moveService(code, "secondary", "primary")}
                      className="text-xs text-gray-400 hover:text-green-600 px-1"
                      title="Move to Primary"
                    >
                      1st
                    </button>
                    <button
                      onClick={() => moveService(code, "secondary", "exclude")}
                      className="text-xs text-gray-400 hover:text-red-600 px-1"
                      title="Exclude"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Excluded */}
          <div className="border border-red-200 rounded-lg p-4 bg-red-50/50">
            <h4 className="text-sm font-semibold text-red-800 mb-3">
              Excluded
              <span className="text-xs font-normal text-red-600 ml-1">
                (skip these)
              </span>
            </h4>
            <div className="space-y-2">
              {services.exclude.map((code) => (
                <div
                  key={code}
                  className="flex items-center justify-between bg-white rounded-lg px-3 py-2 border border-red-200"
                >
                  <span className="text-sm">
                    {SERVICE_TYPE_LABELS[code] || code}
                  </span>
                  <div className="flex gap-1">
                    <button
                      onClick={() => moveService(code, "exclude", "primary")}
                      className="text-xs text-gray-400 hover:text-green-600 px-1"
                      title="Move to Primary"
                    >
                      1st
                    </button>
                    <button
                      onClick={() => moveService(code, "exclude", "secondary")}
                      className="text-xs text-gray-400 hover:text-orange-600 px-1"
                      title="Move to Secondary"
                    >
                      2nd
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Add unassigned services */}
        {unassignedServices.length > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <p className="text-xs text-gray-500 mb-2">
              Add more service types:
            </p>
            <div className="flex flex-wrap gap-2">
              {unassignedServices.map((code) => (
                <button
                  key={code}
                  onClick={() =>
                    setServices((prev) => ({
                      ...prev,
                      secondary: [...prev.secondary, code],
                    }))
                  }
                  className="inline-flex items-center gap-1 px-3 py-1.5 bg-gray-100 text-gray-600 rounded-lg text-xs hover:bg-gray-200 transition-colors"
                >
                  <Plus className="w-3 h-3" />
                  {SERVICE_TYPE_LABELS[code] || code}
                </button>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* ═══ Service Area ═══ */}
      <section className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-navy-900 mb-4 flex items-center gap-2">
          <MapPin className="w-5 h-5 text-gold" /> Service Area
        </h3>

        {/* Postcode Districts */}
        <div className="mb-6">
          <label className="block text-xs text-gray-500 mb-2 uppercase font-medium">
            Postcode Districts
          </label>
          <div className="flex flex-wrap gap-2 mb-3">
            {geo.districts.map((d) => (
              <span
                key={d}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-navy-50 text-navy-900 rounded-lg text-sm"
              >
                {d}
                <button
                  onClick={() =>
                    setGeo({
                      ...geo,
                      districts: geo.districts.filter((x) => x !== d),
                    })
                  }
                  className="text-navy-400 hover:text-red-600"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={newDistrict}
              onChange={(e) => setNewDistrict(e.target.value.toUpperCase())}
              placeholder="e.g. SW19"
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm w-32 focus:ring-2 focus:ring-navy-500 focus:border-transparent"
              onKeyDown={(e) => {
                if (e.key === "Enter" && newDistrict.trim()) {
                  if (!geo.districts.includes(newDistrict.trim())) {
                    setGeo({
                      ...geo,
                      districts: [...geo.districts, newDistrict.trim()],
                    });
                  }
                  setNewDistrict("");
                }
              }}
            />
            <button
              onClick={() => {
                if (newDistrict.trim() && !geo.districts.includes(newDistrict.trim())) {
                  setGeo({
                    ...geo,
                    districts: [...geo.districts, newDistrict.trim()],
                  });
                  setNewDistrict("");
                }
              }}
              className="px-3 py-2 bg-navy-900 text-white rounded-lg text-sm hover:bg-navy-700 transition-colors"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Max Distance */}
        <div className="mb-6">
          <label className="block text-xs text-gray-500 mb-2 uppercase font-medium">
            Max Distance from Office (km)
          </label>
          <div className="flex items-center gap-4">
            <input
              type="range"
              min={1}
              max={30}
              value={geo.max_distance_km}
              onChange={(e) =>
                setGeo({ ...geo, max_distance_km: parseInt(e.target.value) })
              }
              className="flex-1"
            />
            <span className="text-lg font-bold text-navy-900 w-16 text-right">
              {geo.max_distance_km} km
            </span>
          </div>
        </div>

        {/* Borough Councils */}
        <div>
          <label className="block text-xs text-gray-500 mb-2 uppercase font-medium">
            Borough Councils Monitored
          </label>
          <div className="flex flex-wrap gap-2 mb-3">
            {geo.borough_councils.map((c) => (
              <span
                key={c}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 text-blue-900 rounded-lg text-sm capitalize"
              >
                {c}
                <button
                  onClick={() =>
                    setGeo({
                      ...geo,
                      borough_councils: geo.borough_councils.filter(
                        (x) => x !== c
                      ),
                    })
                  }
                  className="text-blue-400 hover:text-red-600"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <select
              value={newCouncil}
              onChange={(e) => setNewCouncil(e.target.value)}
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-navy-500 focus:border-transparent"
            >
              <option value="">Add council...</option>
              {ALL_COUNCILS.filter(
                (c) => !geo.borough_councils.includes(c)
              ).map((c) => (
                <option key={c} value={c}>
                  {c.charAt(0).toUpperCase() + c.slice(1)}
                </option>
              ))}
            </select>
            <button
              onClick={() => {
                if (newCouncil && !geo.borough_councils.includes(newCouncil)) {
                  setGeo({
                    ...geo,
                    borough_councils: [...geo.borough_councils, newCouncil],
                  });
                  setNewCouncil("");
                }
              }}
              disabled={!newCouncil}
              className="px-3 py-2 bg-navy-900 text-white rounded-lg text-sm hover:bg-navy-700 disabled:opacity-50 transition-colors"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
        </div>
      </section>

      {/* ═══ Lead Scoring ═══ */}
      <section className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-navy-900 mb-4 flex items-center gap-2">
          <Target className="w-5 h-5 text-gold" /> Lead Scoring
        </h3>

        {/* Weights */}
        <div className="space-y-4 mb-6">
          {([
            ["geography", "Geography"],
            ["property_value", "Property Value"],
            ["work_type", "Work Type Match"],
            ["timing", "Timing"],
          ] as const).map(([key, label]) => (
            <div key={key} className="flex items-center gap-4">
              <span className="text-sm text-gray-600 w-36">{label}</span>
              <input
                type="range"
                min={0}
                max={50}
                value={scoring.weights[key] || 0}
                onChange={(e) => {
                  setScoring({
                    ...scoring,
                    weights: {
                      ...scoring.weights,
                      [key]: parseInt(e.target.value),
                    },
                  });
                }}
                className="flex-1"
              />
              <span className="text-sm font-bold text-navy-900 w-14 text-right">
                {scoring.weights[key] || 0} pts
              </span>
            </div>
          ))}
          <div className="text-right">
            {(() => {
              const total = Object.values(scoring.weights).reduce(
                (a, b) => a + b,
                0
              );
              return (
                <span
                  className={`text-sm font-bold ${
                    total === 100 ? "text-green-600" : "text-red-600"
                  }`}
                >
                  Total: {total}/100
                  {total !== 100 && " (must equal 100)"}
                </span>
              );
            })()}
          </div>
        </div>

        {/* Thresholds */}
        <div className="grid grid-cols-2 gap-6 pt-4 border-t border-gray-100">
          <div>
            <label className="block text-xs text-gray-500 mb-1">
              Minimum Score (create lead)
            </label>
            <input
              type="number"
              min={0}
              max={100}
              value={scoring.minimum_score}
              onChange={(e) =>
                setScoring({
                  ...scoring,
                  minimum_score: parseInt(e.target.value) || 0,
                })
              }
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-lg font-bold text-navy-900 focus:ring-2 focus:ring-navy-500 focus:border-transparent"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">
              Auto-send Threshold
            </label>
            <input
              type="number"
              min={0}
              max={100}
              value={scoring.auto_send_threshold}
              onChange={(e) =>
                setScoring({
                  ...scoring,
                  auto_send_threshold: parseInt(e.target.value) || 0,
                })
              }
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-lg font-bold text-green-600 focus:ring-2 focus:ring-navy-500 focus:border-transparent"
            />
          </div>
        </div>
      </section>

      {/* ═══ Notifications (read-only for now) ═══ */}
      <section className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-navy-900 mb-4 flex items-center gap-2">
          <Bell className="w-5 h-5 text-gold" /> Notifications
        </h3>
        <dl className="space-y-3">
          {[
            ["Daily Summary", `8:00 AM → ${company.email || "john@smithandsons.co.uk"}`],
            ["Weekly Report", `Monday 9:00 AM → ${company.email || "john@smithandsons.co.uk"}`],
            ["Planning Sync", "Daily at 6:00 AM"],
          ].map(([label, value]) => (
            <div key={label} className="flex justify-between">
              <dt className="text-sm text-gray-600">{label}</dt>
              <dd className="text-sm text-navy-900">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      {/* ═══ Save Button ═══ */}
      <div className="sticky bottom-6 flex justify-end">
        <button
          onClick={handleSave}
          disabled={
            saving ||
            Object.values(scoring.weights).reduce((a, b) => a + b, 0) !== 100
          }
          className="flex items-center gap-2 px-6 py-3 bg-navy-900 text-white rounded-xl text-sm font-semibold hover:bg-navy-700 disabled:opacity-50 shadow-lg transition-all"
        >
          {saving ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Saving...
            </>
          ) : (
            <>
              <Save className="w-4 h-4" />
              Save All Settings
            </>
          )}
        </button>
      </div>
    </div>
  );
}

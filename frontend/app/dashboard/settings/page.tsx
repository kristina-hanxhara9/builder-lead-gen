"use client";

import { useEffect, useState } from "react";
import {
  Bell,
  Building,
  Check,
  Crown,
  Hammer,
  Loader2,
  MapPin,
  Plus,
  Save,
  Shield,
  Target,
  X,
} from "lucide-react";
import { getSettings, updateSettings } from "@/lib/api";
import type { AppSettings, SettingsUpdateRequest } from "@/lib/api";

// ═══════════════════════════════════════════════════════════════
// HARDCODED CLIENT DATA — this is the client's bespoke system
// Change these values per client deployment
// ═══════════════════════════════════════════════════════════════
const CLIENT = {
  name: "Smith & Sons Builders",
  owner: "John Smith",
  phone: "020 7946 0123",
  email: "john@smithandsons.co.uk",
  website: "smithandsons.co.uk",
  address: "123 High Street, Wandsworth, London SW18 2PT",
  companyReg: "12345678",
  vat: "GB 123 4567 89",
  tradingSince: 1998,
  logo: "/logo.png", // optional
};

// Services THIS client actually does — controls what appears in tiers
const CLIENT_SERVICES: Record<string, string> = {
  EXTENSION: "Extensions",
  CONVERSION_LOFT: "Loft Conversions",
  KITCHEN: "Kitchen Extensions",
  CONVERSION_GARAGE: "Garage Conversions",
  BATHROOM: "Bathrooms",
  RENOVATION: "Renovations",
};

// Services to ALWAYS exclude (not in their trade)
const ALWAYS_EXCLUDED_LABELS: Record<string, string> = {
  SOLAR_PV: "Solar PV",
  HEAT_PUMP: "Heat Pumps",
  GENERAL_RENOVATION: "General Renovation",
  NEW_BUILD: "New Builds",
  CONVERSION_BASEMENT: "Basement Conversions",
};

// Known councils in their area
const AVAILABLE_COUNCILS = [
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
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveResult, setSaveResult] = useState<{
    ok: boolean;
    msg: string;
  } | null>(null);

  // ── Editable state (only the parts the client can change) ──
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
    weights: {
      geography: 30,
      property_value: 25,
      work_type: 30,
      timing: 15,
    } as Record<string, number>,
    minimum_score: 65,
    auto_send_threshold: 85,
  });

  const [newDistrict, setNewDistrict] = useState("");
  const [newCouncil, setNewCouncil] = useState("");

  useEffect(() => {
    loadSettings();
  }, []);

  async function loadSettings() {
    setLoading(true);
    try {
      const data = await getSettings();
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

  // ── Service tier helpers (only for CLIENT_SERVICES) ──
  function moveService(
    code: string,
    from: keyof typeof services,
    to: keyof typeof services
  ) {
    setServices((prev) => ({
      ...prev,
      [from]: prev[from].filter((s) => s !== code),
      [to]: [...prev[to].filter((s) => s !== code), code],
    }));
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    );
  }

  const yearsTrading = new Date().getFullYear() - CLIENT.tradingSince;

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

      {/* ═══ Client Branded Header ═══ */}
      <section className="bg-gradient-to-br from-navy-900 to-navy-800 rounded-xl border border-navy-700 p-6 text-white relative overflow-hidden">
        <div className="absolute top-4 right-4">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-gold/20 text-gold rounded-full text-xs font-semibold">
            <Crown className="w-3 h-3" />
            Premium Plan
          </span>
        </div>
        <div className="flex items-start gap-5">
          <div className="w-16 h-16 bg-white/10 rounded-xl flex items-center justify-center flex-shrink-0">
            <Building className="w-8 h-8 text-gold" />
          </div>
          <div>
            <h2 className="text-xl font-bold">{CLIENT.name}</h2>
            <p className="text-navy-200 text-sm mt-1">
              Est. {CLIENT.tradingSince} · {yearsTrading} years in SW London
            </p>
            <div className="grid grid-cols-2 gap-x-8 gap-y-1 mt-4 text-sm">
              <div>
                <span className="text-navy-300">Owner:</span>{" "}
                <span className="text-white font-medium">{CLIENT.owner}</span>
              </div>
              <div>
                <span className="text-navy-300">Phone:</span>{" "}
                <span className="text-white font-medium">{CLIENT.phone}</span>
              </div>
              <div>
                <span className="text-navy-300">Email:</span>{" "}
                <span className="text-white font-medium">{CLIENT.email}</span>
              </div>
              <div>
                <span className="text-navy-300">Website:</span>{" "}
                <span className="text-white font-medium">
                  {CLIENT.website}
                </span>
              </div>
              <div className="col-span-2">
                <span className="text-navy-300">Office:</span>{" "}
                <span className="text-white font-medium">
                  {CLIENT.address}
                </span>
              </div>
            </div>
          </div>
        </div>
        <p className="mt-4 text-xs text-navy-300 flex items-center gap-1.5">
          <Shield className="w-3 h-3" />
          To update company details, contact your account manager.
        </p>
      </section>

      {/* ═══ Your Services ═══ */}
      <section className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-navy-900 mb-1 flex items-center gap-2">
          <Hammer className="w-5 h-5 text-gold" /> Your Services
        </h3>
        <p className="text-xs text-gray-500 mb-4">
          Control which planning applications your system targets.{" "}
          <strong>Primary</strong> = top priority (full score),{" "}
          <strong>Secondary</strong> = also interested (partial score),{" "}
          <strong>Not interested</strong> = skip these leads.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Primary */}
          <div className="border-2 border-green-200 rounded-xl p-4 bg-green-50/30">
            <h4 className="text-sm font-bold text-green-800 mb-3 flex items-center gap-1.5">
              <span className="w-2 h-2 bg-green-500 rounded-full" />
              Core Services
              <span className="text-xs font-normal text-green-600 ml-auto">
                100% score
              </span>
            </h4>
            <div className="space-y-2">
              {services.primary
                .filter((code) => code in CLIENT_SERVICES)
                .map((code) => (
                  <div
                    key={code}
                    className="flex items-center justify-between bg-white rounded-lg px-3 py-2.5 border border-green-200 shadow-sm"
                  >
                    <span className="text-sm font-medium">
                      {CLIENT_SERVICES[code] || code}
                    </span>
                    <button
                      onClick={() =>
                        moveService(code, "primary", "secondary")
                      }
                      className="text-xs text-gray-400 hover:text-orange-600 px-2 py-0.5 rounded hover:bg-orange-50 transition-colors"
                      title="Move to Secondary"
                    >
                      ↓
                    </button>
                  </div>
                ))}
              {services.primary.filter((code) => code in CLIENT_SERVICES)
                .length === 0 && (
                <p className="text-xs text-gray-400 italic py-2">
                  Drag services here
                </p>
              )}
            </div>
          </div>

          {/* Secondary */}
          <div className="border-2 border-orange-200 rounded-xl p-4 bg-orange-50/30">
            <h4 className="text-sm font-bold text-orange-800 mb-3 flex items-center gap-1.5">
              <span className="w-2 h-2 bg-orange-500 rounded-full" />
              Also Interested
              <span className="text-xs font-normal text-orange-600 ml-auto">
                50% score
              </span>
            </h4>
            <div className="space-y-2">
              {services.secondary
                .filter((code) => code in CLIENT_SERVICES)
                .map((code) => (
                  <div
                    key={code}
                    className="flex items-center justify-between bg-white rounded-lg px-3 py-2.5 border border-orange-200 shadow-sm"
                  >
                    <span className="text-sm font-medium">
                      {CLIENT_SERVICES[code] || code}
                    </span>
                    <div className="flex gap-1">
                      <button
                        onClick={() =>
                          moveService(code, "secondary", "primary")
                        }
                        className="text-xs text-gray-400 hover:text-green-600 px-2 py-0.5 rounded hover:bg-green-50 transition-colors"
                        title="Move to Core"
                      >
                        ↑
                      </button>
                      <button
                        onClick={() =>
                          moveService(code, "secondary", "exclude")
                        }
                        className="text-xs text-gray-400 hover:text-red-600 px-2 py-0.5 rounded hover:bg-red-50 transition-colors"
                        title="Not interested"
                      >
                        ↓
                      </button>
                    </div>
                  </div>
                ))}
              {services.secondary.filter((code) => code in CLIENT_SERVICES)
                .length === 0 && (
                <p className="text-xs text-gray-400 italic py-2">
                  No secondary services
                </p>
              )}
            </div>
          </div>

          {/* Not Interested */}
          <div className="border-2 border-gray-200 rounded-xl p-4 bg-gray-50/30">
            <h4 className="text-sm font-bold text-gray-600 mb-3 flex items-center gap-1.5">
              <span className="w-2 h-2 bg-gray-400 rounded-full" />
              Not Interested
              <span className="text-xs font-normal text-gray-500 ml-auto">
                skipped
              </span>
            </h4>
            <div className="space-y-2">
              {services.exclude
                .filter((code) => code in CLIENT_SERVICES)
                .map((code) => (
                  <div
                    key={code}
                    className="flex items-center justify-between bg-white rounded-lg px-3 py-2.5 border border-gray-200 shadow-sm"
                  >
                    <span className="text-sm font-medium text-gray-500">
                      {CLIENT_SERVICES[code] || code}
                    </span>
                    <button
                      onClick={() =>
                        moveService(code, "exclude", "secondary")
                      }
                      className="text-xs text-gray-400 hover:text-orange-600 px-2 py-0.5 rounded hover:bg-orange-50 transition-colors"
                      title="Move to Secondary"
                    >
                      ↑
                    </button>
                  </div>
                ))}
              {/* Show always-excluded as locked items */}
              {services.exclude
                .filter((code) => code in ALWAYS_EXCLUDED_LABELS)
                .map((code) => (
                  <div
                    key={code}
                    className="flex items-center justify-between bg-gray-100 rounded-lg px-3 py-2 border border-gray-200 opacity-60"
                  >
                    <span className="text-xs text-gray-400">
                      {ALWAYS_EXCLUDED_LABELS[code] || code}
                    </span>
                    <span className="text-[10px] text-gray-400">
                      not your trade
                    </span>
                  </div>
                ))}
              {services.exclude.filter((code) => code in CLIENT_SERVICES)
                .length === 0 &&
                services.exclude.filter(
                  (code) => code in ALWAYS_EXCLUDED_LABELS
                ).length === 0 && (
                  <p className="text-xs text-gray-400 italic py-2">
                    All services active
                  </p>
                )}
            </div>
          </div>
        </div>
      </section>

      {/* ═══ Your Patch ═══ */}
      <section className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-navy-900 mb-1 flex items-center gap-2">
          <MapPin className="w-5 h-5 text-gold" /> Your Patch
        </h3>
        <p className="text-xs text-gray-500 mb-4">
          We monitor planning applications in these areas for you.
        </p>

        {/* Postcode Districts */}
        <div className="mb-6">
          <label className="block text-xs text-gray-500 mb-2 uppercase font-medium tracking-wide">
            Postcode Districts
          </label>
          <div className="flex flex-wrap gap-2 mb-3">
            {geo.districts.map((d) => (
              <span
                key={d}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-navy-50 text-navy-900 rounded-lg text-sm font-medium"
              >
                {d}
                <button
                  onClick={() =>
                    setGeo({
                      ...geo,
                      districts: geo.districts.filter((x) => x !== d),
                    })
                  }
                  className="text-navy-400 hover:text-red-600 transition-colors"
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
                if (
                  newDistrict.trim() &&
                  !geo.districts.includes(newDistrict.trim())
                ) {
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
          <label className="block text-xs text-gray-500 mb-2 uppercase font-medium tracking-wide">
            Max Distance from Your Office
          </label>
          <div className="flex items-center gap-4">
            <input
              type="range"
              min={1}
              max={30}
              value={geo.max_distance_km}
              onChange={(e) =>
                setGeo({
                  ...geo,
                  max_distance_km: parseInt(e.target.value),
                })
              }
              className="flex-1"
            />
            <span className="text-lg font-bold text-navy-900 w-16 text-right">
              {geo.max_distance_km} km
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            Leads further than this will score lower on geography.
          </p>
        </div>

        {/* Borough Councils */}
        <div>
          <label className="block text-xs text-gray-500 mb-2 uppercase font-medium tracking-wide">
            Councils We&apos;re Monitoring
          </label>
          <div className="flex flex-wrap gap-2 mb-3">
            {geo.borough_councils.map((c) => (
              <span
                key={c}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 text-blue-900 rounded-lg text-sm font-medium capitalize"
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
                  className="text-blue-400 hover:text-red-600 transition-colors"
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
              {AVAILABLE_COUNCILS.filter(
                (c) => !geo.borough_councils.includes(c)
              ).map((c) => (
                <option key={c} value={c}>
                  {c.charAt(0).toUpperCase() + c.slice(1)}
                </option>
              ))}
            </select>
            <button
              onClick={() => {
                if (
                  newCouncil &&
                  !geo.borough_councils.includes(newCouncil)
                ) {
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

      {/* ═══ Lead Quality ═══ */}
      <section className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-navy-900 mb-1 flex items-center gap-2">
          <Target className="w-5 h-5 text-gold" /> Lead Quality
        </h3>
        <p className="text-xs text-gray-500 mb-4">
          Fine-tune how we score and filter leads for you. Higher thresholds =
          fewer but better quality leads.
        </p>

        {/* Weights */}
        <div className="space-y-4 mb-6">
          {(
            [
              [
                "geography",
                "Geography",
                "How close is the property to your office?",
              ],
              [
                "property_value",
                "Property Value",
                "Higher value properties = bigger projects",
              ],
              [
                "work_type",
                "Work Type Match",
                "Does this match your core services?",
              ],
              [
                "timing",
                "Timing",
                "How recently was the application submitted?",
              ],
            ] as const
          ).map(([key, label, hint]) => (
            <div key={key}>
              <div className="flex items-center gap-4">
                <span className="text-sm text-gray-700 w-36 font-medium">
                  {label}
                </span>
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
              <p className="text-[11px] text-gray-400 ml-40">{hint}</p>
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
                  {total !== 100 && " — adjust sliders to total 100"}
                </span>
              );
            })()}
          </div>
        </div>

        {/* Thresholds */}
        <div className="grid grid-cols-2 gap-6 pt-4 border-t border-gray-100">
          <div>
            <label className="block text-xs text-gray-500 mb-1">
              Minimum Score to Create Lead
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
            <p className="text-[11px] text-gray-400 mt-1">
              Below this score, we won&apos;t create a lead
            </p>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">
              Auto-send Letter Threshold
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
            <p className="text-[11px] text-gray-400 mt-1">
              Above this score, letters send automatically
            </p>
          </div>
        </div>
      </section>

      {/* ═══ Notifications ═══ */}
      <section className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-navy-900 mb-4 flex items-center gap-2">
          <Bell className="w-5 h-5 text-gold" /> Your Notifications
        </h3>
        <dl className="space-y-3">
          {[
            [
              "Daily Lead Summary",
              `8:00 AM → ${CLIENT.email}`,
            ],
            [
              "Weekly Performance Report",
              `Monday 9:00 AM → ${CLIENT.email}`,
            ],
            ["Planning Portal Sync", "Daily at 6:00 AM — automatic"],
          ].map(([label, value]) => (
            <div key={label} className="flex justify-between items-center">
              <dt className="text-sm text-gray-600">{label}</dt>
              <dd className="text-sm text-navy-900 font-medium">{value}</dd>
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
            Object.values(scoring.weights).reduce((a, b) => a + b, 0) !==
              100
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
              Save Settings
            </>
          )}
        </button>
      </div>
    </div>
  );
}

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function getScoreColor(score: number): string {
  if (score >= 85) return "text-green-600 bg-green-50";
  if (score >= 65) return "text-yellow-600 bg-yellow-50";
  return "text-red-600 bg-red-50";
}

export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    new: "bg-blue-100 text-blue-800",
    contacted: "bg-yellow-100 text-yellow-800",
    quoted: "bg-purple-100 text-purple-800",
    won: "bg-green-100 text-green-800",
    lost: "bg-gray-100 text-gray-800",
    draft: "bg-gray-100 text-gray-800",
    approved: "bg-blue-100 text-blue-800",
    queued: "bg-yellow-100 text-yellow-800",
    printed: "bg-indigo-100 text-indigo-800",
    posted: "bg-purple-100 text-purple-800",
    delivered: "bg-green-100 text-green-800",
  };
  return colors[status] || "bg-gray-100 text-gray-800";
}

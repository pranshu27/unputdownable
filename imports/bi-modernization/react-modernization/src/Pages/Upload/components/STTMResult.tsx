import React from "react";
import * as XLSX from "xlsx";
import {
    ArrowLeft,
    Download,
    CheckCircle,
    Table as TableIcon,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from '../../CodeGen/CodeGenComponents/button.tsx';

export default function ResultsScreen({ data, onBack }) {
    const navigate = useNavigate();

    const { total_rows, mapping } = data;
    const columns =
        mapping && mapping.length > 0 ? Object.keys(mapping[0]) : [];

    const handleDownload = () => {
        const worksheet = XLSX.utils.json_to_sheet(mapping);

        const colWidths = columns.map((col) => {
            const maxLen = Math.max(
                col.length,
                ...mapping.map((row) =>
                    row[col] != null ? String(row[col]).length : 0
                )
            );
            return { wch: Math.min(maxLen + 2, 40) };
        });

        worksheet["!cols"] = colWidths;

        const workbook = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(workbook, worksheet, "STTM Mapping");
        XLSX.writeFile(workbook, "sttm_mapping.xlsx");
    };

    return (
        <div>


            {/* 🔹 Top Section */}
            <div className="flex items-center justify-between mb-10">
                <div>
                    <h2 className="text-3xl font-bold text-gray-800">
                        Mapping Results
                    </h2>
                    <p className="text-gray-500 text-sm mt-1">
                        Source-to-target mapping generated successfully
                    </p>
                </div>

                <div className="flex gap-3">
                    {/* Reset Mapping */}
                    <button
                        onClick={onBack}
                        className="flex items-center gap-2 px-4 py-2 rounded-lg border text-gray-600 hover:border-blue-500 hover:text-blue-600 transition"
                    >
                        New Mapping
                    </button>

                    {/* Download */}
                    <button
                        onClick={handleDownload}
                        className="flex items-center gap-2 px-5 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 shadow transition"
                    >
                        <Download className="w-4 h-4" />
                        Download Excel
                    </button>
                </div>
            </div>

            {/* 🔹 Success Card */}
            <div className="bg-green-50 border border-green-200 rounded-xl p-5 flex items-center gap-4 mb-8">
                <CheckCircle className="text-green-600 w-6 h-6" />
                <div>
                    <div className="font-semibold text-green-700">
                        Mapping Generated Successfully
                    </div>
                    <div className="text-sm text-green-600">
                        {total_rows} rows · {columns.length} columns
                    </div>
                </div>
            </div>

            {/* 🔹 Stats */}
            <div className="grid md:grid-cols-3 gap-6 mb-8">
                <StatCard label="Status" value="Success" />
                <StatCard label="Total Rows" value={total_rows} />
                <StatCard label="Columns" value={columns.length} />
            </div>

            {/* 🔹 Table */}
            <div className="bg-white rounded-2xl shadow-sm border overflow-hidden">
                <div className="flex items-center justify-between px-6 py-4 border-b bg-gray-50">
                    <div className="flex items-center gap-2">
                        <TableIcon className="w-5 h-5 text-gray-500" />
                        <h3 className="font-semibold text-gray-700">
                            Source-to-Target Mapping
                        </h3>
                    </div>

                    <span className="text-xs text-gray-500">
                        {total_rows} rows · {columns.length} columns
                    </span>
                </div>

                <div className="overflow-auto max-h-[500px]">
                    <table className="min-w-full text-sm">
                        <thead className="bg-gray-100 sticky top-0">
                            <tr>
                                {columns.map((col) => {
                                    const displayName =
                                        col.toLowerCase() === "Description"
                                            ? "Description / Transformation"
                                            : col;

                                    return (
                                        <th
                                            key={col}
                                            className="px-4 py-3 text-left font-semibold text-gray-600 uppercase text-xs tracking-wide"
                                        >
                                            {displayName}
                                        </th>
                                    );
                                })}
                            </tr>
                        </thead>


                        <tbody>
                            {mapping.map((row, idx) => (
                                <tr
                                    key={idx}
                                    className="border-t hover:bg-blue-50 transition"
                                >
                                    {columns.map((col) => (
                                        <td
                                            key={col}
                                            className="px-4 py-3 text-gray-700 whitespace-nowrap"
                                            title={
                                                row[col] != null ? String(row[col]) : ""
                                            }
                                        >
                                            {row[col] != null ? String(row[col]) : ""}
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}

/* 🔹 Stat Card */
function StatCard({ label, value }) {
    return (
        <div className="bg-white rounded-xl border p-6 shadow-sm">
            <div className="text-xs text-gray-500 uppercase tracking-wide mb-2">
                {label}
            </div>
            <div className="text-2xl font-bold text-gray-800">
                {value}
            </div>
        </div>
    );
}

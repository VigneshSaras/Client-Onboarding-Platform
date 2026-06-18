"use client";
import React, { useState, useEffect, useRef } from "react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

interface EvaluationResult {
  company_id: string;
  company_name: string;
  scores: {
    alltables_score: number;
    business_logic_score: number;
    combined_overall_score: number;
  };
  findings: {
    critical_count: number;
    high_count: number;
    low_count: number;
  };
  improvements: any[];
  summary: {
    strengths: string[];
    weaknesses: string[];
    recommendation: string;
  };
  grade: string;
  cost?: {
    total: number;
    tokens: number;
  };
  last_week_score?: number;
  this_week_score?: number;
  delta?: number;
}

interface CostSummary {
  total_calls: number;
  total_tokens: number;
  total_cost: number;
  avg_cost_per_eval: number;
}

export default function Home() {
  const [activeTab, setActiveTab] = useState<"onboard" | "results">("onboard");
  const [env, setEnv] = useState("dev");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [productType, setProductType] = useState("Saras IQ");
  const [revenue, setRevenue] = useState("<$15M");
  const [password, setPassword] = useState("Test@1234");
  const [projectId, setProjectId] = useState("");
  const [dataset, setDataset] = useState("");

  const [logicFiles, setLogicFiles] = useState<FileList | null>(null);
  const [yamlFiles, setYamlFiles] = useState<FileList | null>(null);

  const [logs, setLogs] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [evaluationResults, setEvaluationResults] = useState<EvaluationResult[]>([]);
  const [selectedCompany, setSelectedCompany] = useState<EvaluationResult | null>(null);
  const [costSummary, setCostSummary] = useState<CostSummary | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Load evaluation results on page load
  useEffect(() => {
    fetchEvaluationResults();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setLogs(["[System] Initializing Onboarding Pipeline...", "[System] Connecting to Python Backend..."]);

    const formData = new FormData();
    formData.append("env", env);
    formData.append("first_name", firstName);
    formData.append("last_name", lastName);
    formData.append("email", email);
    formData.append("company_name", companyName);
    formData.append("product_type", productType);
    formData.append("revenue", revenue);
    formData.append("password", password);
    formData.append("project_id", projectId);
    formData.append("dataset", dataset);

    if (logicFiles) {
      for (let i = 0; i < logicFiles.length; i++) {
        formData.append("logic_files", logicFiles[i]);
      }
    }
    if (yamlFiles) {
      for (let i = 0; i < yamlFiles.length; i++) {
        formData.append("yaml_files", yamlFiles[i]);
      }
    }

    try {
      // Connect to the dynamically configured FastAPI server (Render or Local)
      const res = await fetch(`${BACKEND_URL}/api/onboard`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();

      if (data.job_id) {
        setLogs((prev) => [...prev, `[System] Job spawned with ID: ${data.job_id}`]);
        connectSSE(data.job_id);
      } else {
        setLogs((prev) => [...prev, `[Error] Failed to start job: ${JSON.stringify(data)}`]);
        setIsSubmitting(false);
      }
    } catch (err: any) {
      setLogs((prev) => [...prev, `[Network Error] Could not connect to API: ${err.message}`]);
      setIsSubmitting(false);
    }
  };

  const connectSSE = (jobId: string) => {
    const evtSource = new EventSource(`${BACKEND_URL}/api/logs/${jobId}`);

    evtSource.onmessage = (event) => {
      const msg = event.data;
      if (msg === "[PROCESS_COMPLETE]") {
        setLogs((prev) => [...prev, "[System] Pipeline Execution Finished."]);
        // Fetch evaluation results
        fetchEvaluationResults();
        evtSource.close();
        setIsSubmitting(false);
      } else {
        setLogs((prev) => [...prev, msg]);
      }
    };

    evtSource.onerror = () => {
      setLogs((prev) => [...prev, "[System] Disconnected from log stream."]);
      evtSource.close();
      setIsSubmitting(false);
    };
  };

  const fetchEvaluationResults = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/evaluation-results`);
      const data = await res.json();
      setEvaluationResults(data.results || []);

      // Extract cost summary from logs or API response
      if (data.results && data.results.length > 0) {
        // Calculate summary from results
        const totalCost = data.results.reduce((sum: number, r: EvaluationResult) => sum + (r.cost?.total || 0), 0);
        const totalTokens = data.results.reduce((sum: number, r: EvaluationResult) => sum + (r.cost?.tokens || 0), 0);
        setCostSummary({
          total_calls: data.results.length * 2, // Estimate 2 API calls per company
          total_tokens: totalTokens,
          total_cost: totalCost,
          avg_cost_per_eval: totalCost / data.results.length
        });
      }
    } catch (err: any) {
      console.error("Failed to fetch evaluation results:", err);
    }
  };

  const startEvaluation = async () => {
    setIsEvaluating(true);
    setLogs(["[System] Starting IQ Configuration Evaluation...", "[System] Connecting to Python Backend..."]);

    try {
      const res = await fetch(`${BACKEND_URL}/api/start-evaluation`, {
        method: "POST",
      });
      const data = await res.json();

      if (data.job_id) {
        setLogs((prev) => [...prev, `[System] Job spawned with ID: ${data.job_id}`]);
        connectEvaluationSSE(data.job_id);
      } else {
        setLogs((prev) => [...prev, `[Error] Failed to start evaluation: ${JSON.stringify(data)}`]);
        setIsEvaluating(false);
      }
    } catch (err: any) {
      setLogs((prev) => [...prev, `[Network Error] Could not connect to API: ${err.message}`]);
      setIsEvaluating(false);
    }
  };

  const connectEvaluationSSE = (jobId: string) => {
    const evtSource = new EventSource(`${BACKEND_URL}/api/evaluation-logs/${jobId}`);

    evtSource.onmessage = (event) => {
      const msg = event.data;
      if (msg === "[PROCESS_COMPLETE]") {
        setLogs((prev) => [...prev, "[System] Evaluation Complete. Loading results..."]);
        // Fetch evaluation results
        fetchEvaluationResults();
        evtSource.close();
        setIsEvaluating(false);
        setActiveTab("results");
      } else {
        setLogs((prev) => [...prev, msg]);
      }
    };

    evtSource.onerror = () => {
      setLogs((prev) => [...prev, "[System] Disconnected from log stream."]);
      evtSource.close();
      setIsEvaluating(false);
    };
  };

  return (
    <main className="min-h-screen bg-neutral-950 text-white font-sans p-8 flex flex-col md:flex-row gap-8">
      {/* LEFT COLUMN: TABS */}
      <section className={`${activeTab === "results" && !selectedCompany ? "w-full" : "w-full md:w-1/2"} bg-neutral-900 border border-neutral-800 rounded-2xl p-8 shadow-2xl flex flex-col gap-6 overflow-hidden transition-all`} style={{ maxHeight: "90vh" }}>
        {/* TAB BUTTONS */}
        <div className="flex gap-2 border-b border-neutral-800 pb-4 justify-between items-center">
          <div className="flex gap-2">
            <button
              onClick={() => setActiveTab("onboard")}
              className={`px-4 py-2 rounded-t-lg font-semibold transition-all ${
                activeTab === "onboard"
                  ? "bg-blue-600 text-white"
                  : "bg-neutral-800 text-neutral-400 hover:text-neutral-300"
              }`}
            >
              Onboarding
            </button>
            <button
              onClick={() => {
                setActiveTab("results");
                fetchEvaluationResults();
              }}
              className={`px-4 py-2 rounded-t-lg font-semibold transition-all ${
                activeTab === "results"
                  ? "bg-blue-600 text-white"
                  : "bg-neutral-800 text-neutral-400 hover:text-neutral-300"
              }`}
            >
              Evaluation Results
            </button>
          </div>
          {activeTab === "results" && (
            <button
              onClick={fetchEvaluationResults}
              className="px-3 py-1 text-xs bg-green-600 hover:bg-green-500 rounded-lg text-white transition-all"
            >
              Refresh
            </button>
          )}
        </div>

        {/* ONBOARDING TAB */}
        {activeTab === "onboard" && (
        <div className="overflow-y-auto flex-1">
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-indigo-500 bg-clip-text text-transparent">
            Saras Client Onboarding
          </h1>
          <p className="text-neutral-400 mt-2 text-sm">Fill out the details to provision a new client environment fully autonomously.</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          {/* Environment */}
          <div className="flex flex-col gap-2">
            <label className="text-sm font-semibold text-neutral-300 uppercase tracking-widest">Environment</label>
            <select value={env} onChange={(e) => setEnv(e.target.value)} className="p-3 bg-neutral-800 rounded-lg border border-neutral-700 outline-none focus:border-blue-500 transition-colors">
              <option value="dev">Development (DEV)</option>
              <option value="test">Test (TEST)</option>
              <option value="prod">Production (PROD)</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <label className="text-sm text-neutral-400">First Name</label>
              <input required value={firstName} onChange={(e) => setFirstName(e.target.value)} type="text" className="p-3 bg-neutral-800 rounded-lg border border-neutral-700 outline-none focus:border-blue-500" />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-sm text-neutral-400">Last Name</label>
              <input required value={lastName} onChange={(e) => setLastName(e.target.value)} type="text" className="p-3 bg-neutral-800 rounded-lg border border-neutral-700 outline-none focus:border-blue-500" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <label className="text-sm text-neutral-400">Company Name</label>
              <input required value={companyName} onChange={(e) => setCompanyName(e.target.value)} type="text" className="p-3 bg-neutral-800 rounded-lg border border-neutral-700 outline-none focus:border-blue-500" />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-sm text-neutral-400">Work Email</label>
              <input required value={email} onChange={(e) => setEmail(e.target.value)} type="email" className="p-3 bg-neutral-800 rounded-lg border border-neutral-700 outline-none focus:border-blue-500" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <label className="text-sm text-neutral-400">New User Password</label>
              <input required value={password} onChange={(e) => setPassword(e.target.value)} type="text" className="p-3 bg-neutral-800 rounded-lg border border-neutral-700 outline-none focus:border-blue-500" />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-sm text-neutral-400">Product</label>
              <select value={productType} onChange={(e) => setProductType(e.target.value)} className="p-3 bg-neutral-800 rounded-lg border border-neutral-700 outline-none focus:border-blue-500">
                <option value="Saras IQ">Saras IQ</option>
                <option value="Saras Pulse">Saras Pulse</option>
              </select>
            </div>
          </div>

          <div className="h-px w-full bg-neutral-800 my-2" />

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <label className="text-sm text-blue-400 font-semibold">GCP Project ID</label>
              <input required value={projectId} onChange={(e) => setProjectId(e.target.value)} type="text" placeholder="e.g. insightsprod" className="p-3 bg-neutral-800 rounded-lg border border-neutral-700 outline-none focus:border-blue-500" />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-sm text-blue-400 font-semibold">BigQuery Dataset</label>
              <input required value={dataset} onChange={(e) => setDataset(e.target.value)} type="text" placeholder="e.g. sandbox_pulse" className="p-3 bg-neutral-800 rounded-lg border border-neutral-700 outline-none focus:border-blue-500" />
            </div>
          </div>

          <div className="h-px w-full bg-neutral-800 my-2" />

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <label className="text-sm text-neutral-400">Business Logic Files (Optional)</label>
              <input type="file" multiple onChange={(e) => setLogicFiles(e.target.files)} className="p-2 text-sm text-neutral-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-900 file:text-blue-300 hover:file:bg-blue-800" />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-sm text-neutral-400">YAML Files (Optional)</label>
              <input type="file" multiple onChange={(e) => setYamlFiles(e.target.files)} className="p-2 text-sm text-neutral-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-indigo-900 file:text-indigo-300 hover:file:bg-indigo-800" />
            </div>
          </div>

          <button disabled={isSubmitting} type="submit" className={`mt-4 p-4 rounded-xl font-bold tracking-wide transition-all ${isSubmitting ? "bg-neutral-800 text-neutral-500 cursor-not-allowed" : "bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-500/20 hover:shadow-blue-500/40"}`}>
            {isSubmitting ? "Orchestrating Pipeline..." : "Deploy Provisioning Pipeline"}
          </button>
        </form>
        </div>
        )}

        {/* RESULTS TAB */}
        {activeTab === "results" && (
        <div className="overflow-y-auto flex-1 flex flex-col">
          <div className="mb-4">
            <button
              onClick={startEvaluation}
              disabled={isEvaluating}
              className={`px-6 py-3 rounded-xl font-bold tracking-wide transition-all ${
                isEvaluating
                  ? "bg-neutral-800 text-neutral-500 cursor-not-allowed"
                  : "bg-green-600 hover:bg-green-500 text-white shadow-lg shadow-green-500/20 hover:shadow-green-500/40"
              }`}
            >
              {isEvaluating ? "Evaluating..." : "START Evaluation"}
            </button>
          </div>

          {evaluationResults.length === 0 ? (
            <div className="text-center text-neutral-500 py-8">
              <p>Click START to run IQ configuration evaluation across all companies.</p>
            </div>
          ) : (
            <div className="overflow-x-auto flex-1">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-neutral-700 sticky top-0 bg-neutral-850">
                    <th className="px-8 py-4 text-left text-xs font-semibold text-neutral-400 uppercase min-w-48">Company Name</th>
                    <th className="px-8 py-4 text-left text-xs font-semibold text-neutral-400 uppercase min-w-24">ID</th>
                    <th className="px-8 py-4 text-center text-xs font-semibold text-neutral-400 uppercase min-w-20">AllTables</th>
                    <th className="px-8 py-4 text-center text-xs font-semibold text-neutral-400 uppercase min-w-20">BL</th>
                    <th className="px-8 py-4 text-center text-xs font-semibold text-neutral-400 uppercase min-w-20">Combined</th>
                    <th className="px-8 py-4 text-center text-xs font-semibold text-neutral-400 uppercase min-w-20">Last Week</th>
                    <th className="px-8 py-4 text-center text-xs font-semibold text-neutral-400 uppercase min-w-20">Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {evaluationResults.map((result) => (
                    <tr
                      key={result.company_id}
                      onClick={() => setSelectedCompany(result)}
                      className={`border-b border-neutral-700 cursor-pointer transition-all ${
                        selectedCompany?.company_id === result.company_id
                          ? "bg-blue-600 bg-opacity-20"
                          : "bg-neutral-800 hover:bg-neutral-700"
                      }`}
                    >
                      <td className="px-8 py-4 text-sm font-bold text-yellow-300 bg-neutral-800">{result.company_name}</td>
                      <td className="px-8 py-4 text-sm text-neutral-300">{result.company_id}</td>
                      <td className="px-8 py-4 text-sm text-center text-blue-400 font-semibold">{result.scores.alltables_score.toFixed(1)}</td>
                      <td className="px-8 py-4 text-sm text-center text-indigo-400 font-semibold">{result.scores.business_logic_score.toFixed(1)}</td>
                      <td className="px-8 py-4 text-sm text-center text-green-400 font-semibold">{result.scores.combined_overall_score.toFixed(1)}</td>
                      <td className="px-8 py-4 text-sm text-center text-gray-400">{(result.last_week_score || 0).toFixed(1)}</td>
                      <td className={`px-8 py-4 text-sm text-center font-semibold ${
                        (result.delta || 0) > 0 ? "text-green-400" : (result.delta || 0) < 0 ? "text-red-400" : "text-neutral-400"
                      }`}>
                        {(result.delta || 0) > 0 ? "+" : ""}{(result.delta || 0).toFixed(1)}
                      </td>
                    </tr>
                  ))}
                  {costSummary && (
                    <tr className="bg-neutral-750 border-t-2 border-neutral-600">
                      <td colSpan={5} className="px-8 py-3">
                        <div className="flex justify-between items-center text-xs gap-4">
                          <div className="text-neutral-400">
                            <span className="font-semibold">Total API Calls:</span> {costSummary.total_calls}
                          </div>
                          <div className="text-neutral-400">
                            <span className="font-semibold">Total Tokens:</span> {costSummary.total_tokens.toLocaleString()}
                          </div>
                          <div className="text-green-400 font-semibold">
                            Total Cost: ${costSummary.total_cost.toFixed(4)}
                          </div>
                          <div className="text-blue-400">
                            <span className="font-semibold">Avg Cost/Eval:</span> ${costSummary.avg_cost_per_eval.toFixed(4)}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
        )}
      </section>

      {/* RIGHT COLUMN: TERMINAL OR DETAIL PANEL OVERLAY */}
      <section className={`${activeTab === "results" && !selectedCompany ? "hidden" : "w-full md:w-1/2"} flex flex-col gap-4 relative transition-all`}>
        {activeTab === "onboard" && (
          <div className="flex-1 bg-black rounded-2xl border border-neutral-800 p-6 overflow-y-auto font-mono text-sm leading-relaxed shadow-inner">
            <h2 className="text-xl font-bold text-neutral-300 flex items-center gap-3 mb-4">
              <span className="w-3 h-3 rounded-full bg-green-500 animate-pulse" />
              Live Terminal Stream
            </h2>
            {logs.length === 0 ? (
              <p className="text-neutral-600 italic">No active pipelines. Waiting for deployment command...</p>
            ) : (
              logs.map((log, idx) => (
                <div key={idx} className={`${log.includes("ERROR") || log.includes("Error") ? "text-red-400" : log.includes("SUCCESS") || log.includes("Finished") ? "text-green-400" : "text-neutral-300"} mb-1`}>
                  {log}
                </div>
              ))
            )}
            <div ref={logsEndRef} />
          </div>
        )}

        {/* DETAIL PANEL - APPEARS ONLY IN RESULTS TAB WHEN COMPANY SELECTED */}
        {activeTab === "results" && selectedCompany && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-end md:items-center justify-end z-50">
            <div className="w-full md:w-1/2 h-4/5 md:h-auto bg-neutral-900 border border-neutral-800 rounded-2xl p-6 overflow-y-auto shadow-2xl max-h-screen">
              {/* CLOSE BUTTON */}
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-bold text-white">{selectedCompany.company_name}</h3>
                <button
                  onClick={() => setSelectedCompany(null)}
                  className="text-neutral-400 hover:text-white text-2xl w-8 h-8 flex items-center justify-center rounded-lg hover:bg-neutral-800 transition-all"
                >
                  ×
                </button>
              </div>

              {/* GRADE & BASIC METRICS */}
              <div className="grid grid-cols-2 gap-3 mb-4">
                <div className="bg-neutral-800 rounded-lg p-3">
                  <p className="text-xs text-neutral-400 uppercase mb-1">Grade</p>
                  <p className={`text-3xl font-bold ${
                    selectedCompany.grade === "A" ? "text-green-400" :
                    selectedCompany.grade === "B" ? "text-blue-400" :
                    selectedCompany.grade === "C" ? "text-yellow-400" :
                    selectedCompany.grade === "D" ? "text-orange-400" :
                    "text-red-400"
                  }`}>
                    {selectedCompany.grade}
                  </p>
                </div>
                <div className="bg-neutral-800 rounded-lg p-3">
                  <p className="text-xs text-neutral-400 uppercase mb-2">Critical Issues</p>
                  <p className="text-2xl font-bold text-red-400">{selectedCompany.findings.critical_count}</p>
                </div>
              </div>

              {/* IMPROVEMENTS */}
              <div className="mb-4">
                <h4 className="text-sm font-semibold text-neutral-300 uppercase mb-3">Key Improvements</h4>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {selectedCompany.improvements.slice(0, 5).map((imp, i) => (
                    <div key={i} className="bg-neutral-800 rounded-lg p-3">
                      <div className="flex items-start justify-between mb-1">
                        <p className="text-xs font-semibold text-neutral-200">{imp.title}</p>
                        <span className={`text-xs font-bold px-2 py-1 rounded whitespace-nowrap ${
                          imp.priority === "critical" ? "bg-red-600 text-white" :
                          imp.priority === "high" ? "bg-orange-600 text-white" :
                          "bg-yellow-600 text-white"
                        }`}>
                          {imp.priority}
                        </span>
                      </div>
                      <p className="text-xs text-neutral-400">{imp.description}</p>
                      <p className="text-xs text-green-400 mt-1">Impact: +{imp.score_delta.toFixed(1)} pts</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* SUMMARY */}
              <div className="space-y-3">
                <div>
                  <p className="text-xs font-semibold text-neutral-400 uppercase mb-2">Recommendation</p>
                  <p className="text-sm text-neutral-300">{selectedCompany.summary.recommendation}</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}

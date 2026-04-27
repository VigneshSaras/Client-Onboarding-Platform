"use client";
import React, { useState, useEffect, useRef } from "react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export default function Home() {
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
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

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

  return (
    <main className="min-h-screen bg-neutral-950 text-white font-sans p-8 flex flex-col md:flex-row gap-8">
      {/* LEFT COLUMN: FORM */}
      <section className="w-full md:w-1/2 bg-neutral-900 border border-neutral-800 rounded-2xl p-8 shadow-2xl flex flex-col gap-6 overflow-y-auto" style={{ maxHeight: "90vh" }}>
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
      </section>

      {/* RIGHT COLUMN: TERMINAL */}
      <section className="w-full md:w-1/2 flex flex-col gap-4">
        <h2 className="text-xl font-bold text-neutral-300 flex items-center gap-3">
          <span className="w-3 h-3 rounded-full bg-green-500 animate-pulse" />
          Live Terminal Stream
        </h2>
        
        <div className="flex-1 bg-black rounded-2xl border border-neutral-800 p-6 overflow-y-auto font-mono text-sm leading-relaxed shadow-inner" style={{ maxHeight: "85vh" }}>
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
      </section>
    </main>
  );
}

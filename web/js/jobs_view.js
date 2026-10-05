// Floating panel listing background jobs with live progress.
import { requestJson } from "./api.js";
import { createElement, showToast } from "./dom.js";
import { liveEvents } from "./live.js";

const jobsByIdentifier = new Map();
const FINISHED_JOB_DISPLAY_LIMIT = 4;
const JOB_STATUS_LABELS = { running: "En cours", completed: "Terminé", failed: "Échec", cancelled: "Annulé" };

function renderJob(job) {
  const progressPercent = job.progress_total ? Math.min(100, Math.round((100 * job.progress_current) / job.progress_total)) : 0;
  const isRunning = job.status === "running";
  const progressBar = createElement("div", {
    className: `progress-bar ${isRunning && !job.progress_total ? "indeterminate" : ""}`,
    style: `width: ${isRunning ? progressPercent : 100}%`,
  });
  return createElement("div", { className: "job" }, [
    createElement("div", { className: "job-header" }, [
      createElement("span", { className: "job-label", text: job.label }),
      createElement("span", { className: "tag", text: JOB_STATUS_LABELS[job.status] || job.status }),
      isRunning ? createElement("button", { className: "button ghost small", text: "Annuler", onClick: () => requestJson(`/api/jobs/${job.id}/cancel`, { method: "POST" }) }) : null,
    ]),
    job.progress_total ? createElement("div", { className: "job-message", text: `${job.progress_current} / ${job.progress_total}` }) : null,
    createElement("div", { className: "progress" }, progressBar),
    createElement("div", { className: "job-message", text: job.error || job.message }),
  ]);
}

function renderJobs() {
  const sortedJobs = [...jobsByIdentifier.values()].sort((first, second) => second.id - first.id);
  const runningJobs = sortedJobs.filter((job) => job.status === "running");
  const finishedJobs = sortedJobs.filter((job) => job.status !== "running").slice(0, FINISHED_JOB_DISPLAY_LIMIT);
  document.getElementById("jobs-list").replaceChildren(...[...runningJobs, ...finishedJobs].map(renderJob));
  document.getElementById("running-job-count").textContent = runningJobs.length;
  document.getElementById("jobs-panel").classList.toggle("collapsed", runningJobs.length === 0);
}

function storeJob(job) {
  const previousJob = jobsByIdentifier.get(job.id);
  jobsByIdentifier.set(job.id, job);
  if (previousJob && previousJob.status === "running" && job.status !== "running") {
    if (job.status === "completed") showToast(`✅ ${job.label} : terminé`);
    if (job.status === "failed") showToast(`❌ ${job.label} : ${job.error}`, "error");
    liveEvents.dispatchEvent(new CustomEvent("job.finished", { detail: job }));
  }
}

export function initializeJobsView() {
  const jobsPanel = document.getElementById("jobs-panel");
  document.getElementById("jobs-toggle").addEventListener("click", () => jobsPanel.classList.toggle("collapsed"));
  liveEvents.addEventListener("jobs.snapshot", (snapshotEvent) => {
    snapshotEvent.detail.forEach(storeJob);
    renderJobs();
  });
  liveEvents.addEventListener("job.updated", (jobEvent) => {
    storeJob(jobEvent.detail);
    renderJobs();
  });
}

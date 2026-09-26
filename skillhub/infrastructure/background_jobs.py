"""One background operation at a time, with cooperative cancellation."""
import threading

class BackgroundJobs:
    def __init__(self):
        self.lock = threading.RLock()
        self.jobs = {}
    def submit(self, run_id, operation):
        with self.lock:
            if any(j["thread"].is_alive() for j in self.jobs.values()):
                return {"error": "已有任务正在运行，请先停止或等待完成。 / A task is already running."}
            event = threading.Event()
            job = {"cancel": event, "error": ""}
            def work():
                try:
                    operation(event.is_set)
                except Exception:
                    job["error"] = "任务未能完成，请检查数据是否可写。 / Background operation failed."
            job["thread"] = threading.Thread(target=work, daemon=True, name="skillhub-agent")
            self.jobs = {run_id: job}
            job["thread"].start()
            return {"ok": True, "run_id": run_id}
    def cancel(self, run_id):
        with self.lock:
            job = self.jobs.get(run_id)
            if not job or not job["thread"].is_alive():
                return False
            job["cancel"].set()
            return True
    def status(self, run_id):
        with self.lock:
            job = self.jobs.get(run_id)
            return {"busy": bool(job and job["thread"].is_alive()),
                    "stop_requested": bool(job and job["cancel"].is_set()),
                    "job_error": job["error"] if job else ""}

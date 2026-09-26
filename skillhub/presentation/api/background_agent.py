"""Background bridge operations keep progress observable without blocking UI."""
from skillhub.infrastructure.background_jobs import BackgroundJobs

class BackgroundAgentApiMixin:
    _background_jobs = BackgroundJobs()
    def can_close_window(self):
        with self._background_jobs.lock:
            busy = any(j["thread"].is_alive() for j in self._background_jobs.jobs.values())
        if busy:
            window = getattr(self, "_window", None)
            if window:
                window.evaluate_js("showToast('任务仍在执行，请先停止或等待完成。 / Stop the running task before closing.', 'warning')")
            return False
        return True

    def agent_start_async(self, goal, session_id="", project_path=""):
        with self._background_jobs.lock:
            if any(j["thread"].is_alive() for j in self._background_jobs.jobs.values()):
                return {"error": "已有任务运行中 / A task is already running"}
            if not self.deepseek_api_key:
                return {"error": "请先配置 API Key / Configure an API key first"}
            runtime = self._agent_runtime()
            result = runtime.start(goal, session_id=session_id, project_path=project_path,
                conversation_context=self._agent_conversation_context(session_id), deferred=True)
            if result.get("error") or result.get("status") != "running":
                self._finish_agent_result(result)
                return result
            run_id = result["run_id"]
            def operation(cancel):
                runtime.cancel_requested = cancel
                self._finish_agent_result(runtime.resume(run_id))
            submitted = self._background_jobs.submit(run_id, operation)
            return submitted if submitted.get("error") else result
    def agent_continue_async(self, run_id, approval_id=""):
        if not self.deepseek_api_key:
            return {"error": "请先配置 API Key / Configure an API key first"}
        runtime = self._agent_runtime()
        def operation(cancel):
            runtime.cancel_requested = cancel
            result = runtime.approve(run_id, approval_id) if approval_id else runtime.resume(run_id)
            if result.get("error"):
                raise ValueError(result["error"])
            self._finish_agent_result(result)
        return self._background_jobs.submit(run_id, operation)
    def _finish_agent_result(self, result):
        if not result.get("final_answer") or not result.get("session_id"):
            return
        repository = self._session_repository()
        with repository.transaction():
            service = self._chat_session_service()
            loaded = service.load_session(result["session_id"])
            session = loaded.get("session")
            if not session:
                return
            messages = session["messages"]
            if not any(m.get("run_id") == result["run_id"] for m in messages):
                messages.append({"role": "assistant", "content": result["final_answer"], "run_id": result["run_id"]})
                saved = service.save_session(session["id"], session.get("title", ""), messages)
                if saved.get("error"):
                    raise OSError(saved["error"])

    def agent_poll(self, run_id):
        result = self.agent_get_task(run_id)
        result.update(self._background_jobs.status(run_id))
        return result
    def agent_stop(self, run_id):
        if self._background_jobs.cancel(run_id):
            return {"ok": True, "stop_requested": True}
        return self._agent_runtime().cancel(run_id)

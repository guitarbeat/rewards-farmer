(() => {
	"use strict";

	const ICONS = {
		pending: "○",
		running: "●",
		ok: "✓",
		skip: "–",
		fail: "✕",
	};

	const els = {
		subtitle: document.getElementById("subtitle"),
		setupChip: document.getElementById("setup-chip"),
		runBtn: document.getElementById("run-btn"),
		stopBtn: document.getElementById("stop-btn"),
		openLogsBtn: document.getElementById("open-logs-btn"),
		openProfileBtn: document.getElementById("open-profile-btn"),
		clearLogBtn: document.getElementById("clear-log-btn"),
		progressSummary: document.getElementById("progress-summary"),
		progressGrid: document.getElementById("progress-grid"),
		historyCount: document.getElementById("history-count"),
		historyList: document.getElementById("history-list"),
		logToggle: document.getElementById("log-toggle"),
		logPanel: document.getElementById("log-panel"),
		logView: document.getElementById("log-view"),
		statusDot: document.getElementById("status-dot"),
		statusText: document.getElementById("status-text"),
		runCount: document.getElementById("run-count"),
		alertDialog: document.getElementById("alert-dialog"),
		alertMessage: document.getElementById("alert-message"),
	};

	let logVisible = false;
	let logLineCount = 0;
	let selectedRun = null;
	let historyFingerprint = "";
	const MAX_LOG_LINES = 4000;

	function showAlert(message) {
		els.alertMessage.textContent = message;
		if (typeof els.alertDialog.showModal === "function") {
			els.alertDialog.showModal();
		} else {
			window.alert(message);
		}
	}

	function api() {
		return window.pywebview && window.pywebview.api;
	}

	async function call(method, ...args) {
		const bridge = api();
		if (!bridge || typeof bridge[method] !== "function") {
			throw new Error("Launcher bridge is not ready yet.");
		}
		return bridge[method](...args);
	}

	function applySnapshot(snapshot) {
		if (!snapshot) return;

		els.subtitle.textContent = snapshot.subtitle || "";
		els.setupChip.textContent = snapshot.setup_strip || "";
		els.progressSummary.textContent = snapshot.progress_summary || "—";
		els.statusText.textContent = snapshot.status_text || "";
		els.runCount.textContent = snapshot.run_count_label || "0 runs";
		els.runBtn.textContent = snapshot.run_button_text || "Run";
		els.runBtn.disabled = !snapshot.run_enabled;
		els.stopBtn.disabled = !snapshot.stop_enabled;

		const tone = snapshot.status_tone || "idle";
		els.statusDot.className = `status-dot tone-${tone}`;

		renderProgress(snapshot.progress_rows || []);
		renderHistory(snapshot.run_history || []);
	}

	function renderProgress(rows) {
		els.progressGrid.replaceChildren();
		for (const row of rows) {
			const state = row.state || "pending";
			const card = document.createElement("article");
			card.className = `step-row is-${state}`;
			card.dataset.step = row.name;

			const accent = document.createElement("div");
			accent.className = "accent";
			accent.setAttribute("aria-hidden", "true");

			const body = document.createElement("div");
			body.className = "body";

			const icon = document.createElement("div");
			icon.className = "icon";
			icon.textContent = ICONS[state] || ICONS.pending;

			const text = document.createElement("div");
			const name = document.createElement("div");
			name.className = "name";
			name.textContent = row.name;
			const detail = document.createElement("div");
			detail.className = "detail";
			detail.textContent = row.detail || "";
			text.append(name, detail);
			body.append(icon, text);
			card.append(accent, body);
			els.progressGrid.append(card);
		}
	}

	function historyKey(entries) {
		return entries
			.map((e) => `${e.number}:${e.finished || ""}:${e.exit_code}:${e.summary}`)
			.join("|");
	}

	function renderHistory(entries) {
		const count = entries.length;
		els.historyCount.textContent = String(count);

		const nextKey = historyKey(entries);
		if (nextKey === historyFingerprint && els.historyList.childElementCount === count) {
			for (const btn of els.historyList.querySelectorAll(".history-item")) {
				const num = Number(btn.dataset.run);
				btn.classList.toggle("is-selected", selectedRun === num);
			}
			return;
		}
		historyFingerprint = nextKey;

		els.historyList.replaceChildren();
		if (!count) {
			const empty = document.createElement("p");
			empty.className = "history-empty";
			empty.textContent = "No past runs yet. Finished runs will show up here.";
			els.historyList.append(empty);
			return;
		}

		for (const entry of entries) {
			const btn = document.createElement("button");
			btn.type = "button";
			btn.className = "history-item";
			btn.dataset.run = String(entry.number);
			btn.setAttribute("role", "listitem");
			if (selectedRun === entry.number) {
				btn.classList.add("is-selected");
			}

			const top = document.createElement("div");
			top.className = "history-top";

			const title = document.createElement("span");
			title.className = "history-title";
			title.textContent = `Run #${entry.number}`;

			const when = document.createElement("span");
			when.className = "history-when";
			when.textContent = entry.started || "";

			const tone = document.createElement("span");
			tone.className = `history-tone tone-${entry.tone || "idle"}`;
			tone.textContent = entry.tone === "success" ? "OK" : entry.tone === "danger" ? "Error" : entry.tone === "warning" ? "Warn" : "—";

			top.append(title, when, tone);

			const summary = document.createElement("div");
			summary.className = "history-summary";
			summary.textContent = entry.summary || "";

			const meta = document.createElement("div");
			meta.className = "history-meta";
			const bits = [];
			if (entry.ok_count) bits.push(`${entry.ok_count} OK`);
			if (entry.skip_count) bits.push(`${entry.skip_count} skip`);
			if (entry.fail_count) bits.push(`${entry.fail_count} fail`);
			if (entry.search_quota) bits.push(`searches ${entry.search_quota}`);
			if (entry.exit_code !== null && entry.exit_code !== undefined) {
				bits.push(`exit ${entry.exit_code}`);
			}
			meta.textContent = bits.join(" · ");

			btn.append(top, summary);
			if (bits.length) btn.append(meta);

			btn.addEventListener("click", () => selectRun(entry.number));
			els.historyList.append(btn);
		}
	}

	async function selectRun(runNumber) {
		selectedRun = runNumber;
		for (const btn of els.historyList.querySelectorAll(".history-item")) {
			btn.classList.toggle("is-selected", Number(btn.dataset.run) === runNumber);
		}

		try {
			const result = await call("get_run_log", runNumber);
			const text = (result && result.text) || "";
			els.logView.replaceChildren();
			logLineCount = 0;
			if (text) {
				appendLogs([{ text, tag: null }]);
			}
			setLogVisible(true);
		} catch (err) {
			showAlert(String(err));
		}
	}

	function appendLogs(logs) {
		if (!logs || !logs.length) return;

		const fragment = document.createDocumentFragment();
		for (const entry of logs) {
			const span = document.createElement("span");
			if (entry.tag) span.className = `tag-${entry.tag}`;
			span.textContent = entry.text;
			fragment.append(span);
			logLineCount += (entry.text.match(/\n/g) || []).length || 1;
		}
		els.logView.append(fragment);

		while (logLineCount > MAX_LOG_LINES && els.logView.firstChild) {
			const first = els.logView.firstChild;
			const text = first.textContent || "";
			logLineCount -= (text.match(/\n/g) || []).length || 1;
			first.remove();
		}

		els.logView.scrollTop = els.logView.scrollHeight;
	}

	function setLogVisible(visible) {
		logVisible = visible;
		els.logPanel.hidden = !visible;
		els.logPanel.classList.toggle("is-collapsed", !visible);
		els.logToggle.textContent = visible ? "Hide" : "Show";
	}

	async function poll() {
		try {
			const result = await call("poll");
			if (selectedRun === null) {
				appendLogs(result.logs || []);
			}
			applySnapshot(result.snapshot);
		} catch (err) {
			console.error(err);
		}
	}

	async function bootstrap() {
		const result = await call("bootstrap");
		els.logView.replaceChildren();
		logLineCount = 0;
		selectedRun = null;
		appendLogs(result.logs || []);
		applySnapshot(result.snapshot);
	}

	els.runBtn.addEventListener("click", async () => {
		try {
			selectedRun = null;
			const result = await call("start_run");
			if (result && result.error) {
				const title =
					/Setup|Missing|data-dir/i.test(result.error) ? "Setup required" : "Could not start";
				showAlert(`${title}\n\n${result.error}`);
			}
			await poll();
		} catch (err) {
			showAlert(String(err));
		}
	});

	els.stopBtn.addEventListener("click", async () => {
		await call("stop_run");
		await poll();
	});

	els.clearLogBtn.addEventListener("click", async () => {
		const result = await call("clear_log");
		if (result && result.error) {
			showAlert(result.error);
			return;
		}
		els.logView.replaceChildren();
		logLineCount = 0;
		selectedRun = null;
		historyFingerprint = "";
		await poll();
	});

	els.openLogsBtn.addEventListener("click", () => call("open_logs"));
	els.openProfileBtn.addEventListener("click", () => call("open_profile"));
	els.logToggle.addEventListener("click", () => setLogVisible(!logVisible));

	document.addEventListener("keydown", (event) => {
		if ((event.ctrlKey || event.metaKey) && (event.key === "Enter" || event.key.toLowerCase() === "r")) {
			event.preventDefault();
			els.runBtn.click();
		}
		if (event.key === "Escape") {
			els.stopBtn.click();
		}
	});

	function ready(fn) {
		if (window.pywebview && window.pywebview.api) {
			fn();
			return;
		}
		window.addEventListener("pywebviewready", fn, { once: true });
	}

	ready(async () => {
		try {
			await bootstrap();
			setInterval(poll, 100);
		} catch (err) {
			showAlert(`Failed to start UI: ${err}`);
		}
	});
})();

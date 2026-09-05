// X-COM Web frontend (js-dos v7.5.0)
window.addEventListener('DOMContentLoaded', function() {
  (function () {
    "use strict";

  const SAVE_SLOTS = 10;
  const BUNDLE_URL = "/game/xcom-jsdos.zip";
  let token = localStorage.getItem("xcom_token") || "";
  let username = localStorage.getItem("xcom_user") || "";
  let ci = null;
  let dos = null;
  let started = false;

  // --- DOM ---
  const authScreen = document.getElementById("auth-screen");
  const gameScreen = document.getElementById("game-screen");
  const authMsg = document.getElementById("auth-msg");
  const whoEl = document.getElementById("who");
  const slotsList = document.getElementById("slots-list");
  const slotsMsg = document.getElementById("slots-msg");
  const jsdosContainer = document.getElementById("jsdos-container");
  const jsdosRoot = document.getElementById("jsdos-root");

  // Debug panel elements
  const debugPanel = document.getElementById("debug-panel");
  const debugOutput = document.getElementById("debug-output");
  const debugClearBtn = document.getElementById("debug-clear-btn");

  // Debug helper
  function logDebug(msg, type) {
    if (!debugPanel) return;
    debugPanel.classList.remove("hidden");
    var entry = document.createElement("div");
    entry.className = "log-entry" + (type ? " " + type : "");
    entry.textContent = msg;
    debugOutput.appendChild(entry);
    debugOutput.scrollTop = debugOutput.scrollHeight;
  }

  // Debug clear handler
  if (debugClearBtn) {
    debugClearBtn.addEventListener("click", function () {
      if (debugOutput) {
        debugOutput.innerHTML = "";
      }
    });
  }

  function setAuthMsg(text, isError) {
    authMsg.textContent = text;
    authMsg.style.color = isError ? "#ff6b6b" : "#8b949e";
  }

  function showSlots(slots) {
    slotsList.innerHTML = "";
    slots.forEach(function (s) {
      var row = document.createElement("div");
      row.className = "slot-row";
      var num = document.createElement("span");
      num.className = "slot-num";
      num.textContent = (s.slot + 1) + ":";
      var btn = document.createElement("button");
      btn.className = "btn";
      btn.textContent = "Load";
      btn.addEventListener("click", function () {
        saveSlot(s.slot);
        loadSlot(s.slot);
      });
      row.appendChild(num);
      row.appendChild(btn);
      slotsList.appendChild(row);
    });
  }

  function api(path, opts) {
    return fetch(path, opts);
  }

  // --- Event bindings ---
  document.getElementById("login-btn").addEventListener("click", login);
  document.getElementById("register-btn").addEventListener("click", register);
  document.getElementById("save-btn").addEventListener("click", function () {
    saveSlot(0);
  });
  document.getElementById("load-btn").addEventListener("click", function () {
    loadSlot(0);
  });
  document.getElementById("logout-btn").addEventListener("click", function () {
    logout();
  });

  async function login() {
    logDebug("[login] starting login attempt", "info");
    try {
      var r = await api("/api/login", {
        method: "POST",
        body: JSON.stringify({
          username: document.getElementById("username").value,
          password: document.getElementById("password").value,
        }),
      });
      var d = await r.json();
      logDebug("[login] server response: status=" + r.status + " data=" + JSON.stringify(d), "info");
      if (r.ok) {
        token = d.token;
        localStorage.setItem("xcom_token", token);
        username = document.getElementById("username").value;
        localStorage.setItem("xcom_user", username);
        logDebug("[login] token stored, switching to game screen", "info");
        authScreen.classList.add("hidden");
        gameScreen.classList.remove("hidden");
        whoEl.textContent = "User: " + username;
        logDebug("[login] game screen visible, calling launch()", "info");
        launch();
      } else {
        logDebug("[login] login failed: " + d.message, "warn");
        setAuthMsg("Login failed: " + d.message, true);
      }
    } catch (e) {
      logDebug("[login] error: " + e.message, "error");
      setAuthMsg("Login error", true);
    }
  }

  async function register() {
    logDebug("[register] starting registration attempt", "info");
    try {
      var r = await api("/api/register", {
        method: "POST",
        body: JSON.stringify({
          username: document.getElementById("username").value,
          password: document.getElementById("password").value,
        }),
      });
      var d = await r.json();
      logDebug("[register] server response: status=" + r.status + " data=" + JSON.stringify(d), "info");
      if (r.ok) {
        logDebug("[register] registration successful", "info");
        setAuthMsg("Registered. Try logging in.");
      } else {
        logDebug("[register] register failed: " + d.message, "warn");
        setAuthMsg("Register failed: " + d.message, true);
      }
    } catch (e) {
      logDebug("[register] error: " + e.message, "error");
      setAuthMsg("Register error", true);
    }
  }

  // --- Game ---
  function launch() {
    if (started) return;
    started = true;

    logDebug("[launch] jsdosRoot=" + jsdosRoot.tagName, "info");
    logDebug("[launch] bundleURL=" + BUNDLE_URL, "info");

    if (typeof window.Dos !== "function") {
      logDebug("[launch] window.Dos is NOT a function", "error");
      started = false;
      return;
    }
    logDebug("[launch] calling window.Dos(jsdosRoot, options)", "info");

    try {
      // window.Dos returns a DosPlayer instance
      dos = window.Dos(jsdosRoot, {
        onReady: function () {
          logDebug("[launch] Player UI ready", "info");
        },
        onError: function (err) {
          logDebug("[launch] Dos error: " + err.message, "error");
        }
      });
      logDebug("[launch] Player instance created, calling .run()", "info");

      // dos.run() loads the game bundle and returns the controller interface (ci)
      dos.run(BUNDLE_URL)
        .then(function(ci_) {
          logDebug("[launch] .run() resolved, emulator started", "info");
          ci = ci_;
          logDebug("[launch] emulator running (game starts via dosbox.conf autoexec)", "info");
        })
        .catch(function(err) {
          logDebug("[launch] .run() rejected: " + err.message, "error");
          started = false;
        });

    } catch (e) {
      logDebug("[launch] Player creation error: " + e.message, "error");
      started = false;
    }
  }


  // --- Slots ---
  async function saveSlot(idx) {
    logDebug("[saveSlot] saving slot " + idx, "info");
    try {
      var r = await api("/api/save", { method: "POST", body: JSON.stringify({ slot: idx }) });
      var d = await r.json();
      logDebug("[saveSlot] response: status=" + r.status + " data=" + JSON.stringify(d), "info");
      if (r.ok) {
        slotsMsg.textContent = "Saved to slot " + (idx + 1);
        logDebug("[saveSlot] save successful", "info");
      } else {
        slotsMsg.textContent = "Save failed: " + d.message;
        logDebug("[saveSlot] save failed: " + d.message, "warn");
      }
    } catch (e) {
      slotsMsg.textContent = "Save error";
      logDebug("[saveSlot] error: " + e.message, "error");
    }
  }

  async function loadSlot(idx) {
    logDebug("[loadSlot] loading slot " + idx, "info");
    try {
      var r = await api("/api/load", { method: "POST", body: JSON.stringify({ slot: idx }) });
      var d = await r.json();
      logDebug("[loadSlot] response: status=" + r.status + " data=" + JSON.stringify(d), "info");
      if (r.ok) {
        slotsMsg.textContent = "Loaded from slot " + (idx + 1);
        logDebug("[loadSlot] load successful", "info");
      } else {
        slotsMsg.textContent = "Load failed: " + d.message;
        logDebug("[loadSlot] load failed: " + d.message, "warn");
      }
    } catch (e) {
      slotsMsg.textContent = "Load error";
      logDebug("[loadSlot] error: " + e.message, "error");
    }
  }

  function logout() {
    logDebug("[logout] logging out", "info");
    token = "";
    username = "";
    localStorage.removeItem("xcom_token");
    localStorage.removeItem("xcom_user");
    started = false;
    authScreen.classList.remove("hidden");
    gameScreen.classList.add("hidden");
    slotsList.innerHTML = "";
    slotsMsg.textContent = "";
    logDebug("[logout] returned to login screen", "info");
  }

  // --- Init ---
  if (typeof window.emulators === "undefined") {
    logDebug("[init] emulators global NOT found — js-dos not loaded", "error");
  } else {
    logDebug("[init] emulators global exists", "info");
    window.emulators.pathPrefix = "/static/js-dos/";
    window.emulators.emulatorFunction = "backend";
    logDebug("[init] pathPrefix set to /static/js-dos/", "info");
    if (typeof window.jsdos === "function") {
      logDebug("[init] jsdos() found, ready", "info");
    } else {
      logDebug("[init] jsdos() not found — no factory", "warn");
    }
  }
})();
});

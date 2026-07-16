// ============================================================
// FITI — frontend logic
// ============================================================

const API_BASE = window.FITI_API_BASE || "http://localhost:8000";

const state = {
  token: localStorage.getItem("fiti_token") || null,
  authMode: "login", // "login" | "signup"
  discoverQueue: [],
  currentMatchId: null,
  matchesCache: [],
  myStatus: { is_premium: false, free_random_remaining: 0, daily_free_random_connects: 3 },
  publicSettings: { unlock_price_ksh: 50, premium_price_ksh: 50 },
  randomQueueId: null,
};

// ---------- helpers ----------

function $(sel) { return document.querySelector(sel); }
function $all(sel) { return document.querySelectorAll(sel); }

async function api(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && state.token) headers["Authorization"] = `Bearer ${state.token}`;

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = "Something went wrong";
    try {
      const errJson = await res.json();
      detail = errJson.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

function setToken(token) {
  state.token = token;
  if (token) localStorage.setItem("fiti_token", token);
  else localStorage.removeItem("fiti_token");
}

function showModal(id) { $(id).classList.remove("hidden"); }
function hideModal(id) { $(id).classList.add("hidden"); }

// ============================================================
// AUTH MODAL
// ============================================================

function openAuth(mode) {
  state.authMode = mode;
  $("#auth-error").textContent = "";
  if (mode === "login") {
    $("#auth-title").textContent = "Karibu back";
    $("#auth-sub").textContent = "Log in to continue to Fiti.";
    $("#auth-submit").textContent = "Log in";
    $("#phone-field").style.display = "none";
    $("#terms-field").style.display = "none";
    $("#switch-text").textContent = "Don't have an account?";
    $("#switch-btn").textContent = "Sign up";
  } else {
    $("#auth-title").textContent = "Karibu kwa Fiti";
    $("#auth-sub").textContent = "Create your account to start matching.";
    $("#auth-submit").textContent = "Create account";
    $("#phone-field").style.display = "block";
    $("#terms-field").style.display = "block";
    $("#switch-text").textContent = "Already have an account?";
    $("#switch-btn").textContent = "Log in";
  }
  showModal("#auth-modal");
}

$("#nav-login").addEventListener("click", () => openAuth("login"));
$("#nav-signup").addEventListener("click", () => openAuth("signup"));
$("#hero-login").addEventListener("click", () => openAuth("login"));
$("#hero-signup").addEventListener("click", () => openAuth("signup"));
$("#auth-close").addEventListener("click", () => hideModal("#auth-modal"));
$("#switch-btn").addEventListener("click", () => openAuth(state.authMode === "login" ? "signup" : "login"));

$("#auth-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = $("#auth-email").value.trim();
  const password = $("#auth-password").value;
  const phone = $("#auth-phone").value.trim();
  $("#auth-error").textContent = "";

  if (state.authMode === "signup" && !$("#auth-terms").checked) {
    $("#auth-error").textContent = "Please confirm you're 18+ and agree to the community guidelines.";
    return;
  }

  try {
    let result;
    if (state.authMode === "signup") {
      result = await api("/auth/register", {
        method: "POST",
        auth: false,
        body: { email, password, phone: phone || null },
      });
    } else {
      result = await api("/auth/login", {
        method: "POST",
        auth: false,
        body: { email, password },
      });
    }
    setToken(result.access_token);
    hideModal("#auth-modal");
    await afterLogin();
  } catch (err) {
    $("#auth-error").textContent = err.message;
  }
});

// ============================================================
// LOGIN FLOW / APP SHELL SWITCH
// ============================================================

async function afterLogin() {
  // Check if profile exists
  try {
    await api("/profiles/me");
    enterApp();
  } catch (err) {
    // No profile yet -> prompt setup
    showModal("#profile-setup-modal");
  }
}

function enterApp() {
  $("#landing").classList.add("hidden");
  $("#app-shell").classList.add("active");
  loadDiscoverDeck();
  refreshMyStatus();
  loadPublicSettings();
}

function exitApp() {
  setToken(null);
  clearInterval(randomPollTimer);
  $("#app-shell").classList.remove("active");
  $("#landing").classList.remove("hidden");
}

async function refreshMyStatus() {
  try {
    state.myStatus = await api("/me/status");
    updatePremiumUI();
  } catch (err) {
    // fail quiet
  }
}

async function loadPublicSettings() {
  try {
    state.publicSettings = await api("/settings/public", { auth: false });
    $("#unlock-price").textContent = `KSH ${state.publicSettings.unlock_price_ksh}`;
    $("#premium-price").textContent = `KSH ${state.publicSettings.premium_price_ksh}`;
  } catch (err) {
    // fail quiet, defaults already shown
  }
}

function updatePremiumUI() {
  const isPremium = state.myStatus.is_premium;
  $("#premium-badge").classList.toggle("hidden", !isPremium);
  $("#upgrade-nav-btn").classList.toggle("hidden", isPremium);
  const banner = $("#random-limit-banner");
  if (isPremium) {
    banner.textContent = "★ Premium — unlimited Random Connects";
  } else {
    banner.textContent = `${state.myStatus.free_random_remaining} of ${state.myStatus.daily_free_random_connects} free random connects left today`;
  }
}

$("#logout-btn").addEventListener("click", exitApp);

// Profile setup (first-time)
$("#profile-setup-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#profile-setup-error").textContent = "";
  if (!$("#ps-facebook").value.trim()) {
    $("#profile-setup-error").textContent = "Facebook username is required.";
    return;
  }
  const body = {
    name: $("#ps-name").value.trim(),
    age: parseInt($("#ps-age").value, 10),
    gender: $("#ps-gender").value,
    interested_in: $("#ps-interested").value,
    facebook_username: $("#ps-facebook").value.trim(),
    county: $("#ps-county").value.trim(),
    bio: $("#ps-bio").value.trim(),
    interests: $("#ps-interests").value.trim(),
  };
  try {
    await api("/profiles/me", { method: "POST", body });
    hideModal("#profile-setup-modal");
    enterApp();
  } catch (err) {
    $("#profile-setup-error").textContent = err.message;
  }
});

// ============================================================
// TABS
// ============================================================

$all(".app-tab").forEach((tab) => {
  tab.addEventListener("click", () => switchTab(tab.dataset.tab));
});

function switchTab(name) {
  $all(".app-tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $all(".tab-panel").forEach((p) => p.classList.add("hidden"));
  $(`#tab-${name}`).classList.remove("hidden");

  if (name === "matches") loadMatches();
  if (name === "profile") loadProfileIntoEditor();
  if (name === "random") {
    refreshMyStatus();
    resetRandomUI();
  }
}

$("#chat-back").addEventListener("click", () => switchTab("matches"));

$("#chat-report").addEventListener("click", async () => {
  const match = state.matchesCache.find((m) => m.id === state.currentMatchId);
  if (!match) return;
  const reason = prompt(
    `Block or report ${match.other_profile.name}?\n\nType a short reason to report + block, or leave blank and press OK to just block.`
  );
  if (reason === null) return; // cancelled
  try {
    if (reason.trim()) {
      await api(`/users/${match.other_profile.user_id}/report`, {
        method: "POST",
        body: { reason: reason.trim().slice(0, 100), details: reason.trim() },
      });
    } else {
      await api(`/users/${match.other_profile.user_id}/block`, { method: "POST" });
    }
    alert(`${match.other_profile.name} has been blocked. You won't see each other again.`);
    switchTab("matches");
  } catch (err) {
    alert(`Couldn't complete that action: ${err.message}`);
  }
});

// ============================================================
// DISCOVER / SWIPE DECK
// ============================================================

const AVATAR_GRADIENTS = [
  "linear-gradient(150deg, #E63975, #14132B 75%)",
  "linear-gradient(150deg, #2A9D8F, #14132B 75%)",
  "linear-gradient(150deg, #E8A94C, #14132B 75%)",
  "linear-gradient(150deg, #E63975, #E8A94C)",
];

async function loadDiscoverDeck() {
  const deck = $("#deck");
  deck.innerHTML = `<div class="deck-empty">Loading profiles…</div>`;
  try {
    const profiles = await api("/discover?limit=20");
    state.discoverQueue = profiles;
    renderDeck();
  } catch (err) {
    deck.innerHTML = `<div class="deck-empty">Couldn't load profiles: ${escapeHtml(err.message)}</div>`;
  }
}

function renderDeck() {
  const deck = $("#deck");
  deck.innerHTML = "";

  if (state.discoverQueue.length === 0) {
    deck.innerHTML = `
      <div class="deck-empty">
        <div class="kitenge-strip"></div>
        <h3 style="font-family: var(--font-display);">You're all caught up</h3>
        <p>No new profiles right now — check back soon, or widen your search in your profile.</p>
      </div>`;
    return;
  }

  // Show up to 3 stacked, front one interactive
  const visible = state.discoverQueue.slice(0, 3).reverse();
  visible.forEach((profile, i) => {
    const isFront = i === visible.length - 1;
    const card = document.createElement("div");
    card.className = "swipe-card";
    const gradient = AVATAR_GRADIENTS[profile.id % AVATAR_GRADIENTS.length];
    const interests = (profile.interests || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 5);

    card.innerHTML = `
      <div class="photo" style="background:${gradient};">
        ${profile.photo_url ? `<img src="${escapeAttr(profile.photo_url)}" alt="${escapeAttr(profile.name)}" />` : ""}
      </div>
      <div class="card-info">
        <h3>${escapeHtml(profile.name)}, ${profile.age}</h3>
        <div class="meta">${escapeHtml(profile.county || "Location not set")}</div>
        ${profile.bio ? `<div class="bio">${escapeHtml(profile.bio)}</div>` : ""}
        ${interests.length ? `<div class="interests">${interests.map((t) => `<span class="pill">${escapeHtml(t)}</span>`).join("")}</div>` : ""}
      </div>
    `;
    if (!isFront) {
      const depth = visible.length - 1 - i;
      card.style.transform = `translateY(${depth * 10}px) scale(${1 - depth * 0.04})`;
      card.style.opacity = `${1 - depth * 0.25}`;
      card.style.zIndex = String(10 - depth);
    } else {
      card.style.zIndex = "20";
      card.dataset.front = "true";
    }
    deck.appendChild(card);
  });
}

async function handleSwipe(direction) {
  if (state.discoverQueue.length === 0) return;
  const profile = state.discoverQueue[0];
  const frontCard = document.querySelector('.swipe-card[data-front="true"]');
  if (frontCard) {
    frontCard.style.transition = "transform 0.35s ease, opacity 0.35s ease";
    frontCard.style.transform = direction === "like" ? "translateX(140%) rotate(18deg)" : "translateX(-140%) rotate(-18deg)";
    frontCard.style.opacity = "0";
  }

  try {
    const result = await api("/swipe", {
      method: "POST",
      body: { swiped_id: profile.user_id, direction },
    });
    state.discoverQueue.shift();
    setTimeout(renderDeck, 220);

    if (result.matched) {
      setTimeout(() => showMatchCelebration(profile, result.match_id), 260);
    }
  } catch (err) {
    state.discoverQueue.shift();
    setTimeout(renderDeck, 220);
  }
}

$("#like-btn").addEventListener("click", () => handleSwipe("like"));
$("#pass-btn").addEventListener("click", () => handleSwipe("pass"));

// Basic swipe-by-drag on the front card
let dragStartX = null;
$("#deck").addEventListener("pointerdown", (e) => {
  if (!e.target.closest('.swipe-card[data-front="true"]')) return;
  dragStartX = e.clientX;
});
$("#deck").addEventListener("pointerup", (e) => {
  if (dragStartX === null) return;
  const delta = e.clientX - dragStartX;
  dragStartX = null;
  if (Math.abs(delta) > 90) {
    handleSwipe(delta > 0 ? "like" : "pass");
  }
});

// ============================================================
// MATCH CELEBRATION (Moyo Meter)
// ============================================================

function showMatchCelebration(profile, matchId) {
  $("#match-name").textContent = profile.name;
  $("#match-sub").innerHTML = `You and <span id="match-name">${escapeHtml(profile.name)}</span> both said yes.`;
  state.currentMatchId = matchId;
  state.currentMatchProfile = profile;

  const path = $("#moyo-fill-path");
  const length = path.getTotalLength();
  path.style.strokeDasharray = String(length);
  path.style.strokeDashoffset = String(length);

  showModal("#match-modal");

  // Compatibility score derived from shared interest overlap (demo heuristic), min 68%
  const score = Math.min(97, 68 + ((profile.id * 7) % 30));
  requestAnimationFrame(() => {
    path.style.strokeDashoffset = String(length - (length * score) / 100);
  });

  let current = 0;
  const pctEl = $("#moyo-pct");
  const timer = setInterval(() => {
    current += 2;
    if (current >= score) { current = score; clearInterval(timer); }
    pctEl.textContent = `${current}%`;
  }, 28);
}

$("#match-keep-swiping").addEventListener("click", () => hideModal("#match-modal"));
$("#match-say-hi").addEventListener("click", () => {
  hideModal("#match-modal");
  switchTab("matches");
  if (state.currentMatchId) openChat(state.currentMatchId);
});

// ============================================================
// MATCHES
// ============================================================

async function loadMatches() {
  const grid = $("#matches-grid");
  grid.innerHTML = `<p style="color: var(--ink-soft);">Loading…</p>`;
  try {
    const matches = await api("/matches");
    state.matchesCache = matches;
    if (matches.length === 0) {
      grid.innerHTML = `<p style="color: var(--ink-soft);">No matches yet — keep swiping in Discover!</p>`;
      return;
    }
    grid.innerHTML = "";
    matches.forEach((m) => {
      const tile = document.createElement("button");
      tile.className = "match-tile";
      tile.style.cursor = "pointer";
      const gradient = AVATAR_GRADIENTS[m.other_profile.id % AVATAR_GRADIENTS.length];
      const randomBadge = m.match_type === "random" ? `<span style="background:var(--blue); color:var(--paper); font-size:0.65rem; font-weight:800; padding:1px 6px; border-radius:999px; margin-left:6px;">🎲 RANDOM</span>` : "";
      tile.innerHTML = `
        <div class="thumb" style="background:${gradient};"></div>
        <div class="tile-info">
          <div class="name">${escapeHtml(m.other_profile.name)}, ${m.other_profile.age}${randomBadge}</div>
          <div class="county">${escapeHtml(m.other_profile.county || "")}</div>
        </div>`;
      tile.addEventListener("click", () => openChat(m.id));
      grid.appendChild(tile);
    });
  } catch (err) {
    grid.innerHTML = `<p style="color: var(--pink);">Couldn't load matches: ${escapeHtml(err.message)}</p>`;
  }
}

// ============================================================
// CHAT
// ============================================================

let chatPollTimer = null;

async function openChat(matchId) {
  state.currentMatchId = matchId;
  const match = state.matchesCache.find((m) => m.id === matchId);
  if (match) {
    $("#chat-name").textContent = match.other_profile.name;
    $("#chat-county").textContent = match.other_profile.county || "";
    $("#unlock-name-locked").textContent = match.other_profile.name + "'s";
    if (match.match_type === "random" && match.icebreaker) {
      $("#icebreaker-text").textContent = match.icebreaker;
      $("#icebreaker-banner").classList.remove("hidden");
    } else {
      $("#icebreaker-banner").classList.add("hidden");
    }
  }
  switchTabRaw("chat");
  await loadChatMessages();
  await loadContactStatus();
  clearInterval(chatPollTimer);
  chatPollTimer = setInterval(loadChatMessages, 4000);
}

function switchTabRaw(name) {
  $all(".tab-panel").forEach((p) => p.classList.add("hidden"));
  $(`#tab-${name}`).classList.remove("hidden");
}

async function loadChatMessages() {
  if (!state.currentMatchId) return;
  try {
    const messages = await api(`/matches/${state.currentMatchId}/messages`);
    renderChatMessages(messages);
  } catch (err) {
    // silent fail on poll
  }
}

function renderChatMessages(messages) {
  const log = $("#chat-log");
  const myId = getMyUserIdFromToken();
  const wasAtBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 20;

  log.innerHTML = messages
    .map((m) => {
      const mine = m.sender_id === myId;
      return `<div class="bubble ${mine ? "mine" : "theirs"}">${escapeHtml(m.content)}</div>`;
    })
    .join("");

  if (wasAtBottom || messages.length <= 1) log.scrollTop = log.scrollHeight;
}

$("#chat-send").addEventListener("click", sendChatMessage);
$("#chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendChatMessage();
});

async function sendChatMessage() {
  const input = $("#chat-input");
  const content = input.value.trim();
  if (!content || !state.currentMatchId) return;
  input.value = "";
  try {
    await api(`/matches/${state.currentMatchId}/messages`, {
      method: "POST",
      body: { content },
    });
    await loadChatMessages();
  } catch (err) {
    alert(`Couldn't send message: ${err.message}`);
  }
}

function getMyUserIdFromToken() {
  if (!state.token) return null;
  try {
    const payload = JSON.parse(atob(state.token.split(".")[1]));
    return parseInt(payload.sub, 10);
  } catch (_) {
    return null;
  }
}

// ============================================================
// CONTACT UNLOCK (M-Pesa paywall)
// ============================================================

let unlockPollTimer = null;

async function loadContactStatus() {
  if (!state.currentMatchId) return;
  clearInterval(unlockPollTimer);
  try {
    const contact = await api(`/matches/${state.currentMatchId}/contact`);
    if (contact.unlocked) {
      showUnlocked(contact);
    } else {
      showLocked(contact.price_ksh);
    }
  } catch (err) {
    // fail quiet, leave locked view showing
  }
}

function showLocked(price) {
  $("#unlock-locked").classList.remove("hidden");
  $("#unlock-unlocked").classList.add("hidden");
  $("#unlock-waiting").classList.add("hidden");
  if (price) $("#unlock-price").textContent = `KSH ${price}`;
}

function showUnlocked(contact) {
  $("#unlock-locked").classList.add("hidden");
  $("#unlock-unlocked").classList.remove("hidden");
  $("#unlock-phone-value").textContent = contact.phone || "Not provided";
  $("#unlock-fb-value").textContent = contact.facebook_username || "Not provided";
}

$("#unlock-pay-btn").addEventListener("click", async () => {
  const phone = $("#unlock-phone").value.trim();
  $("#unlock-error").textContent = "";
  if (!phone) {
    $("#unlock-error").textContent = "Enter the M-Pesa number to charge.";
    return;
  }
  $("#unlock-pay-btn").disabled = true;
  try {
    const result = await api(`/matches/${state.currentMatchId}/unlock/initiate`, {
      method: "POST",
      body: { phone },
    });
    if (result.status === "completed") {
      await loadContactStatus();
      return;
    }
    $("#unlock-waiting").classList.remove("hidden");
    unlockPollTimer = setInterval(async () => {
      try {
        const statusResult = await api(`/unlock-payments/${result.payment_id}/status`);
        if (statusResult.unlocked) {
          clearInterval(unlockPollTimer);
          await loadContactStatus();
        } else if (statusResult.status === "failed") {
          clearInterval(unlockPollTimer);
          $("#unlock-waiting").classList.add("hidden");
          $("#unlock-error").textContent = "Payment failed or was cancelled. Try again.";
        }
      } catch (_) {}
    }, 3000);
  } catch (err) {
    $("#unlock-error").textContent = err.message;
  } finally {
    $("#unlock-pay-btn").disabled = false;
  }
});

// ============================================================
// PROFILE EDIT
// ============================================================

async function loadProfileIntoEditor() {
  try {
    const p = await api("/profiles/me");
    $("#pe-name").value = p.name || "";
    $("#pe-age").value = p.age || "";
    $("#pe-gender").value = p.gender || "woman";
    $("#pe-interested").value = p.interested_in || "everyone";
    $("#pe-facebook").value = p.facebook_username || "";
    $("#pe-county").value = p.county || "";
    $("#pe-bio").value = p.bio || "";
    $("#pe-interests").value = p.interests || "";
  } catch (err) {
    $("#profile-edit-error").textContent = err.message;
  }
}

$("#profile-edit-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#profile-edit-error").textContent = "";
  $("#profile-edit-success").textContent = "";
  if (!$("#pe-facebook").value.trim()) {
    $("#profile-edit-error").textContent = "Facebook username is required.";
    return;
  }
  const body = {
    name: $("#pe-name").value.trim(),
    age: parseInt($("#pe-age").value, 10),
    gender: $("#pe-gender").value,
    interested_in: $("#pe-interested").value,
    facebook_username: $("#pe-facebook").value.trim(),
    county: $("#pe-county").value.trim(),
    bio: $("#pe-bio").value.trim(),
    interests: $("#pe-interests").value.trim(),
  };
  try {
    await api("/profiles/me", { method: "PUT", body });
    $("#profile-edit-success").textContent = "Saved!";
    loadDiscoverDeck();
  } catch (err) {
    $("#profile-edit-error").textContent = err.message;
  }
});

// ============================================================
// RANDOM CONNECT (Ablo-style instant pairing)
// ============================================================

let randomPollTimer = null;

function resetRandomUI() {
  clearInterval(randomPollTimer);
  state.randomQueueId = null;
  $("#random-idle").classList.remove("hidden");
  $("#random-waiting").classList.add("hidden");
  $("#random-limit-hit").classList.add("hidden");
}

$("#random-find-btn").addEventListener("click", startRandomFind);
$("#random-cancel-btn").addEventListener("click", resetRandomUI);
$("#random-go-premium-btn").addEventListener("click", () => showModal("#premium-modal"));
$("#upgrade-nav-btn").addEventListener("click", () => showModal("#premium-modal"));

async function startRandomFind() {
  $("#random-idle").classList.add("hidden");
  $("#random-limit-hit").classList.add("hidden");
  $("#random-waiting").classList.remove("hidden");

  try {
    const result = await api("/random/find", { method: "POST" });
    if (result.status === "matched") {
      onRandomMatched(result);
      return;
    }
    // Waiting — poll until someone else joins.
    state.randomQueueId = result.queue_id;
    randomPollTimer = setInterval(pollRandomStatus, 2500);
  } catch (err) {
    if (err.message && err.message.toLowerCase().includes("free random connects")) {
      $("#random-waiting").classList.add("hidden");
      $("#random-limit-hit").classList.remove("hidden");
    } else {
      alert(err.message);
      resetRandomUI();
    }
  }
}

async function pollRandomStatus() {
  if (!state.randomQueueId) return;
  try {
    const result = await api(`/random/status/${state.randomQueueId}`);
    if (result.status === "matched") {
      clearInterval(randomPollTimer);
      onRandomMatched(result);
    }
  } catch (err) {
    clearInterval(randomPollTimer);
  }
}

function onRandomMatched(result) {
  resetRandomUI();
  refreshMyStatus();
  loadMatches();
  switchTab("matches");
  if (result.other_profile) {
    const fakeMatch = {
      id: result.match_id,
      other_profile: result.other_profile,
      match_type: "random",
      icebreaker: result.icebreaker,
    };
    if (!state.matchesCache.find((m) => m.id === result.match_id)) {
      state.matchesCache.push(fakeMatch);
    }
    openChat(result.match_id);
  }
}

// ============================================================
// PREMIUM (one-time "unlock everything")
// ============================================================

let premiumPollTimer = null;

$("#premium-close").addEventListener("click", () => hideModal("#premium-modal"));

$("#premium-pay-btn").addEventListener("click", async () => {
  const phone = $("#premium-phone").value.trim();
  $("#premium-error").textContent = "";
  if (!phone) {
    $("#premium-error").textContent = "Enter your M-Pesa number.";
    return;
  }
  $("#premium-pay-btn").disabled = true;
  try {
    const result = await api("/premium/initiate", { method: "POST", body: { phone } });
    if (result.status === "completed") {
      hideModal("#premium-modal");
      await refreshMyStatus();
      return;
    }
    $("#premium-waiting").classList.remove("hidden");
    premiumPollTimer = setInterval(async () => {
      try {
        const statusResult = await api(`/premium/status/${result.payment_id}`);
        if (statusResult.is_premium) {
          clearInterval(premiumPollTimer);
          $("#premium-waiting").classList.add("hidden");
          hideModal("#premium-modal");
          await refreshMyStatus();
        } else if (statusResult.status === "failed") {
          clearInterval(premiumPollTimer);
          $("#premium-waiting").classList.add("hidden");
          $("#premium-error").textContent = "Payment failed or was cancelled. Try again.";
        }
      } catch (_) {}
    }, 3000);
  } catch (err) {
    $("#premium-error").textContent = err.message;
  } finally {
    $("#premium-pay-btn").disabled = false;
  }
});

// ============================================================
// UTIL
// ============================================================

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
function escapeAttr(str) { return escapeHtml(str); }

// ============================================================
// INIT
// ============================================================

(async function init() {
  if (state.token) {
    try {
      await afterLogin();
    } catch (_) {
      setToken(null);
    }
  }
})();

Auth.requireLogin();

let currentGroupId = null;
let ws = null;
let reconnectAttempts = {};
const MAX_WS_RETRIES = 5;
const WS_RECONNECT_BASE_MS = 2000;
let serverPingInterval = null;

const groupsUl = document.getElementById("groupsUl");
const chatArea = document.getElementById("chatArea");
const currentGroupName = document.getElementById("currentGroupName");
const chatWindow = document.getElementById("chatWindow");
const chatEmpty = document.getElementById("chatEmpty");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const errorBanner = document.getElementById("errorBanner");
const groupsError = document.getElementById("groupsError");
const reconnectBtn = document.getElementById("reconnectBtn");
const btnCatchMeUp = document.getElementById("btnCatchMeUp");

const newGroupName = document.getElementById("newGroupName");
const btnCreateGroup = document.getElementById("btnCreateGroup");

async function loadGroups() {
    try {
        const groups = await apiRequest("/api/groups");
        console.debug("group-chat: loaded groups", groups);
        groupsUl.innerHTML = "";
        if (!groups || groups.length === 0) {
            groupsUl.innerHTML = `
              <li class='text-muted'>No groups found.</li>
              <li style="margin-top:8px;"><button id="refreshGroupsBtn" class="btn btn-secondary" style="width:100%;">Refresh groups</button></li>
            `;
            const refreshBtn = document.getElementById("refreshGroupsBtn");
            if (refreshBtn) refreshBtn.addEventListener('click', loadGroups);
            return;
        }
        
        if (groups.length === 0) {
            groupsUl.innerHTML = "<li class='text-muted'>No groups found.</li>";
            return;
        }

        groups.forEach(g => {
            const li = document.createElement("li");
            li.textContent = g.name;
            if (g.is_member) {
                li.textContent += " (Joined)";
            }
            if (g.id === currentGroupId) {
                li.classList.add("active");
            }
            
            li.addEventListener("click", () => selectGroup(g));
            groupsUl.appendChild(li);
        });
    } catch (err) {
        console.error("group-chat: failed to load groups", err);
        groupsUl.innerHTML = "<li class='text-error'>Failed to load groups.</li>";
        if (groupsError) {
            groupsError.textContent = "Failed to load groups: " + (err && err.message ? err.message : String(err));
            groupsError.classList.add('visible');
        }
        if (errorBanner) {
            errorBanner.textContent = "Failed to load groups: " + (err && err.message ? err.message : String(err));
        }
    }
}

async function selectGroup(group) {
    errorBanner.textContent = "";
    
    if (!group.is_member) {
        try {
            await apiRequest(`/api/groups/${group.id}/join`, { method: "POST" });
            group.is_member = 1;
        } catch (err) {
            errorBanner.textContent = err.message;
            return;
        }
    }
    
    currentGroupId = group.id;
    currentGroupName.textContent = group.name;
    chatArea.style.display = "flex";

    // Show the Catch Me Up button when a group is selected
    const catchMeUpBtn = document.getElementById("catchMeUpBtn");
    if (catchMeUpBtn) catchMeUpBtn.style.display = "flex";

    loadGroups(); // to update active state
    
    try {
        const messages = await apiRequest(`/api/groups/${group.id}/messages`);
        chatWindow.innerHTML = "";
        if (messages.length === 0) {
            chatWindow.appendChild(chatEmpty);
            chatEmpty.style.display = "block";
        } else {
            messages.forEach(appendMessage);
        }
    } catch (err) {
        errorBanner.textContent = "Failed to load messages.";
    }
    
    connectWebSocket(group.id);
}

function connectWebSocket(groupId) {
    if (ws) {
        ws.close();
    }
    
    const token = Auth.getToken();
    if (!token) return;
    
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsHost = window.location.protocol === "file:" ? "localhost:8000" : window.location.host;
    const wsUrl = `${wsProtocol}//${wsHost}/ws/groups/${groupId}?token=${token}`;
    ws = new WebSocket(wsUrl);
    
    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (chatEmpty && chatEmpty.parentNode) {
            chatEmpty.parentNode.removeChild(chatEmpty);
        }
        appendMessage(msg);
    };
    
    ws.onopen = () => {
        console.debug("group-chat: websocket open for group", groupId);
        if (errorBanner) { errorBanner.textContent = ""; hideBanner(errorBanner); }
        if (groupsError) { groupsError.textContent = ""; hideBanner(groupsError); }
        if (reconnectBtn) reconnectBtn.style.display = 'none';
        reconnectAttempts[groupId] = 0;
    };

    ws.onerror = (err) => {
        console.error("WebSocket error", err);
        if (errorBanner) errorBanner.textContent = "WebSocket error (see console).";
    };

    ws.onclose = (ev) => {
        console.warn("group-chat: websocket closed", ev);
        if (errorBanner) { errorBanner.textContent = "Disconnected from chat. Reconnecting..."; showBanner(errorBanner, errorBanner.textContent); }
        if (reconnectBtn) reconnectBtn.style.display = 'inline-block';
        // attempt reconnect with backoff
        reconnectAttempts[groupId] = (reconnectAttempts[groupId] || 0) + 1;
        const attempts = reconnectAttempts[groupId];
        if (attempts <= MAX_WS_RETRIES) {
            // exponential backoff with small jitter
            const jitter = Math.floor(Math.random() * 800);
            const delay = WS_RECONNECT_BASE_MS * Math.pow(2, attempts - 1) + jitter;
            setTimeout(() => {
                if (currentGroupId === groupId) connectWebSocket(groupId);
            }, delay);
        } else {
            // start pinging server periodically and only reconnect when /api/health responds
            if (serverPingInterval) clearInterval(serverPingInterval);
            serverPingInterval = setInterval(() => tryReconnectWhenServerUp(groupId), 5000);
            if (errorBanner) { errorBanner.textContent = "Unable to reconnect to chat automatically. Waiting for server to become available..."; showBanner(errorBanner, errorBanner.textContent); }
            if (reconnectBtn) reconnectBtn.style.display = 'inline-block';
        }
    };
}

async function tryReconnectWhenServerUp(groupId) {
    try {
        const res = await apiRequest('/api/health', { skipAuth: true });
        if (res && res.status === 'ok') {
            console.debug('group-chat: server healthy, attempting reconnect', res);
            if (serverPingInterval) { clearInterval(serverPingInterval); serverPingInterval = null; }
            reconnectAttempts[groupId] = 0;
            connectWebSocket(groupId);
        }
    } catch (err) {
        // server still down — keep polling silently
        console.debug('group-chat: health ping failed', err && err.message ? err.message : err);
    }
}

if (reconnectBtn) {
    reconnectBtn.addEventListener('click', (e) => {
        e.preventDefault();
        if (currentGroupId) {
            if (errorBanner) { errorBanner.textContent = "Reconnecting..."; showBanner(errorBanner, errorBanner.textContent); }
            connectWebSocket(currentGroupId);
        }
    });
}

const catchMeUpBtn = document.getElementById("catchMeUpBtn");
if (catchMeUpBtn) {
    // Hide initially until a group is joined
    catchMeUpBtn.style.display = "none";
    catchMeUpBtn.addEventListener('click', (e) => {
        e.preventDefault();
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            errorBanner.textContent = "Not connected to chat. Please wait...";
            return;
        }
        // Show loading state
        catchMeUpBtn.disabled = true;
        catchMeUpBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation:spin 1s linear infinite"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
            Summarizing...
        `;
        // Send to AI via WebSocket — backend detects @ai + summarize keywords
        ws.send("@ai catch me up — summarize all the recent messages in this group chat into short bullet points");
        // Re-enable button after 5 seconds
        setTimeout(() => {
            catchMeUpBtn.disabled = false;
            catchMeUpBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
                Catch Me Up
            `;
        }, 5000);
    });
}

function appendMessage(msg) {
    const div = document.createElement("div");
    div.classList.add("chat-message");
    
    const user = Auth.getUser();
    const myName = user ? user.name : "";
    
    if (msg.user_id === null) {
        div.classList.add("ai");
    } else if (msg.sender_name === myName) {
        div.classList.add("me");
    } else {
        div.classList.add("other");
    }
    
    const sender = document.createElement("div");
    sender.classList.add("msg-sender");
    sender.textContent = msg.sender_name;
    
    const text = document.createElement("div");
    text.classList.add("msg-text");
    text.textContent = msg.message;
    
    div.appendChild(sender);
    div.appendChild(text);
    
    chatWindow.appendChild(div);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        errorBanner.textContent = "Not connected to chat.";
        return;
    }
    
    const text = chatInput.value.trim();
    if (!text) return;
    
    ws.send(text);
    chatInput.value = "";
});

chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        chatForm.dispatchEvent(new Event("submit"));
    }
});

btnCreateGroup.addEventListener("click", async () => {
    const name = newGroupName.value.trim();
    if (!name) return;
    
    try {
        await apiRequest("/api/groups", { method: "POST", body: { name, description: "" } });
        newGroupName.value = "";
        loadGroups();
    } catch (err) {
        alert("Failed to create group: " + err.message);
    }
});

loadGroups();

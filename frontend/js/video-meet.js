Auth.requireLogin();

const roomNameInput = document.getElementById("roomNameInput");
const btnJoinMeet = document.getElementById("btnJoinMeet");
const jitsiContainer = document.getElementById("jitsi-container");
let apiInst = null;
const meetError = document.getElementById("meetError");
const btnCreateMeet = document.getElementById("btnCreateMeet");
const newMeetInfo = document.getElementById("newMeetInfo");
const newMeetCode = document.getElementById("newMeetCode");
const btnCopyCode = document.getElementById("btnCopyCode");

function generateMeetCode() {
    const chars = 'abcdefghijklmnopqrstuvwxyz';
    let code = '';
    for (let i = 0; i < 9; i++) {
        if (i === 3 || i === 6) code += '-';
        code += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return code;
}

if (btnCreateMeet) {
    btnCreateMeet.addEventListener("click", () => {
        const code = generateMeetCode();
        roomNameInput.value = code;
        newMeetCode.textContent = code;
        newMeetInfo.style.display = "block";
        if (meetError) hideBanner(meetError);
    });
}

if (btnCopyCode) {
    btnCopyCode.addEventListener("click", () => {
        navigator.clipboard.writeText(newMeetCode.textContent).then(() => {
            const oldText = btnCopyCode.textContent;
            btnCopyCode.textContent = "Copied!";
            setTimeout(() => { btnCopyCode.textContent = oldText; }, 2000);
        });
    });
}

btnJoinMeet.addEventListener("click", () => {
    const roomName = roomNameInput.value.trim();
    if (!roomName) {
        if (meetError) showBanner(meetError, "Please enter a room name.");
        else alert("Please enter a room name.");
        return;
    }
    if (meetError) hideBanner(meetError);
    if (apiInst) {
        apiInst.dispose();
    }
    
    const user = Auth.getUser();
    const displayName = user ? user.name : "Student";
    
    const domain = "meet.jit.si";
    const options = {
        roomName: "Trailhead_" + roomName.replace(/[^a-zA-Z0-9]/g, "") + "_SecureRoom2026",
        width: "100%",
        height: "100%",
        parentNode: jitsiContainer,
        userInfo: {
            displayName: displayName
        },
        configOverwrite: {
            startWithAudioMuted: true,
            startWithVideoMuted: true
        }
    };
    
    try {
        if (typeof JitsiMeetExternalAPI === 'undefined') {
            throw new Error('Jitsi Meet API not loaded (external_api.js missing or blocked)');
        }
        apiInst = new JitsiMeetExternalAPI(domain, options);
        document.getElementById("joinForm").style.display = "none";
    } catch (err) {
        console.error('video-meet: failed to start Jitsi', err);
        if (meetError) showBanner(meetError, 'Unable to start meeting: ' + (err && err.message ? err.message : String(err)));
        else alert('Unable to start meeting: ' + (err && err.message ? err.message : String(err)));
        return;
    }
    
    apiInst.addEventListener("readyToClose", () => {
        apiInst.dispose();
        apiInst = null;
        document.getElementById("joinForm").style.display = "flex";
        roomNameInput.value = "";
    });
});

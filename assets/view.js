CTFd._internal.challenge.data = undefined;
CTFd._internal.challenge.renderer = null;
CTFd._internal.challenge.preRender = function () { };
CTFd._internal.challenge.render = null;
CTFd._internal.challenge.postRender = function () {
    var data = CTFd._internal.challenge.data;
    if (data && data.id) initContainerPanel(data.id);
};

CTFd._internal.challenge.submit = function (preview) {
    var challenge_id = parseInt(CTFd.lib.$("#challenge-id").val());
    var submission = CTFd.lib.$("#challenge-input").val().trim();

    resetAlert();

    var body = {
        challenge_id: challenge_id,
        submission: submission,
    };
    var params = {};
    if (preview) {
        params["preview"] = true;
    }

    return CTFd.api.post_challenge_attempt(params, body).then(function (response) {
        return response;
    });
};

function el(id) {
    return document.getElementById(id);
}

// English texts; view.html passes the player's language (pt, ja, ko) in the
// panel's data-texts, and anything missing there falls back to these.
var CONTAINER_TEXTS_EN = {
    loading: "Loading...",
    fetch: "Fetch Instance",
    extend: "Extend +{m}m",
    terminate: "Terminate",
    confirm: "Click again to confirm",
    expired: "Expired",
    expires_s: "Expires in {n} seconds",
    expires_m: "Expires in {n} minutes",
    unknown_time: "unknown",
    starting: "Container is still starting up - this page refreshes automatically.",
    unknown: "Unknown error",
    none: "No active instance. Click 'Fetch Instance' to start.",
    unknown_status: "Unknown status: {s}",
    err_info: "Error fetching container info.",
    err_request: "Error requesting container.",
    err_renew: "Error renewing container.",
    terminated: "Instance terminated.",
    err_stop: "Error stopping container.",
    max: "You have reached the maximum number of concurrent containers ({n})",
    not_running: "No running container found",
    not_available: "Challenge is not available",
    stop_failed: "Failed to stop container"
};

function tr(key, vars) {
    var texts = {};
    var panel = document.querySelector(".deployment-actions");
    try {
        texts = JSON.parse((panel && panel.dataset.texts) || "{}");
    } catch (e) {
        texts = {};
    }
    var text = texts[key] || CONTAINER_TEXTS_EN[key] || key;
    Object.keys(vars || {}).forEach(function (name) {
        text = text.split("{" + name + "}").join(vars[name]);
    });
    return text;
}

// Server messages the player is likely to see, in the player's language
function trServerError(message) {
    var max = /maximum number of concurrent containers \((\d+)\)/.exec(message || "");
    if (max) return tr("max", { n: max[1] });
    var known = {
        "No running container found": "not_running",
        "Challenge is not available": "not_available",
        "Failed to stop container": "stop_failed"
    };
    return known[message] ? tr(known[message]) : message;
}

function setAlert(message, isError) {
    var alert = el("deployment-info");
    if (!alert) return null;
    // textContent everywhere: instance/host data is operator supplied and must
    // never be interpreted as markup.
    alert.textContent = "";
    alert.classList.toggle("alert-danger", !!isError);
    if (message !== undefined && message !== null) {
        alert.append(message);
    }
    return alert;
}

function setButtonsDisabled(disabled) {
    ["create-chal", "extend-chal", "terminate-chal"].forEach(function (id) {
        var button = el(id);
        if (button) button.disabled = disabled;
    });
}

function resetTerminateButton() {
    endTerminateConfirm(el("terminate-chal"));
}

function beginTerminateConfirm(button) {
    button.dataset.confirming = "1";
    button.dataset.originalHtml = button.innerHTML;
    button.classList.add("terminate-confirming");
    // Plain text: a polling refresh must not be able to overwrite the button
    // while the player is deciding.
    button.textContent = tr("confirm");
    button.dataset.resetTimer = String(setTimeout(function () {
        endTerminateConfirm(button);
    }, 5000));
}

function endTerminateConfirm(button) {
    if (!button || button.dataset.confirming !== "1") return;
    clearTimeout(parseInt(button.dataset.resetTimer || "0", 10));
    button.dataset.confirming = "0";
    button.classList.remove("terminate-confirming");
    if (button.dataset.originalHtml) {
        button.innerHTML = button.dataset.originalHtml;
        delete button.dataset.originalHtml;
    }
}

function setRenewLabel(minutes) {
    var button = el("extend-chal");
    if (!button || !minutes) return;
    var label = button.querySelector("small");
    if (label) {
        label.textContent = " " + tr("extend", { m: minutes }) + " ";
    }
}

function resetAlert() {
    var alert = setAlert("");
    if (alert) {
        var spinner = document.createElement("div");
        spinner.className = "spinner-border text-primary";
        spinner.setAttribute("role", "status");
        var hidden = document.createElement("span");
        hidden.className = "visually-hidden";
        hidden.textContent = tr("loading");
        spinner.appendChild(hidden);
        alert.appendChild(spinner);
    }
    setButtonsDisabled(true);
    return alert;
}

function enableButtons() {
    setButtonsDisabled(false);
}

function toggleChallengeCreate() {
    var btn = el("create-chal");
    if (btn) btn.classList.remove("d-none");
}

function hideChallengeCreate() {
    var btn = el("create-chal");
    if (btn) btn.classList.add("d-none");
}

function toggleChallengeUpdate() {
    ["extend-chal", "terminate-chal"].forEach(function (id) {
        var btn = el(id);
        if (btn) btn.classList.remove("d-none");
    });
}

function hideChallengeUpdate() {
    ["extend-chal", "terminate-chal"].forEach(function (id) {
        var btn = el(id);
        if (btn) btn.classList.add("d-none");
    });
    // buttons are hidden only while the instance is gone/stopped, so a
    // half-finished confirmation cannot survive.
    resetTerminateButton();
}

function formatExpiry(timestampMs) {
    if (!timestampMs) return tr("unknown_time");
    var secondsLeft = Math.ceil((timestampMs - Date.now()) / 1000);
    if (secondsLeft < 0) {
        return tr("expired");
    } else if (secondsLeft < 60) {
        return tr("expires_s", { n: secondsLeft });
    }
    return tr("expires_m", { n: Math.ceil(secondsLeft / 60) });
}

function appendLink(parent, url) {
    var link = document.createElement("a");
    link.href = url;
    link.textContent = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    parent.append(link, document.createElement("br"));
}

function appendExtraInfo(parent, info) {
    if (!info) return;
    if (parent.lastChild && parent.lastChild.tagName === "BR") {
        parent.removeChild(parent.lastChild);
    }
    var small = document.createElement("small");
    small.textContent = info;
    parent.append(document.createElement("br"), small);
}

function renderConnectionInfo(connection, parent) {
    if (!connection) return;
    var info = connection.info;

    // Subdomain routing: a list of per-port URLs
    if (connection.type === "url_list" && connection.urls && connection.urls.length) {
        connection.urls.forEach(function (item) {
            appendLink(parent, item.url);
        });
        appendExtraInfo(parent, info);
        return;
    }

    var ports = connection.ports;
    var hasPorts = ports && Object.keys(ports).length > 0;
    var type = (connection.type || "").toLowerCase();

    if (type === "tcp" || type === "nc" || type === "ssh") {
        var targets = hasPorts ? Object.values(ports) : [connection.port];
        targets.forEach(function (external) {
            var code = document.createElement("code");
            if (type === "ssh") {
                code.textContent = "ssh -p " + external + " user@" + connection.host;
            } else {
                code.textContent = "nc " + connection.host + " " + external;
            }
            parent.append(code, document.createElement("br"));
        });
    } else if (type === "https") {
        appendLink(parent, "https://" + connection.host);
    } else if (type === "http" || type === "web" || type === "url") {
        // Containers serve plain HTTP on their published port, even when the
        // CTFd page itself is on HTTPS (use connection type "https" otherwise)
        var scheme = "http://";
        var hosts = hasPorts
            ? Object.values(ports).map(function (external) {
                return scheme + connection.host + ":" + external;
            })
            : [scheme + connection.host + ":" + connection.port];
        hosts.forEach(function (url) { appendLink(parent, url); });
    } else {
        // Unknown/custom type: show host:port pairs
        var pairs = hasPorts
            ? Object.values(ports).map(function (external) {
                return connection.host + ":" + external;
            })
            : [connection.host + ":" + connection.port];
        pairs.forEach(function (pair) {
            var code = document.createElement("code");
            code.textContent = pair;
            parent.append(code, document.createElement("br"));
        });
    }

    appendExtraInfo(parent, info);
}

function applyInstancePayload(data) {
    var alert = setAlert("");
    if (!alert) return;

    if (data.renew_minutes) setRenewLabel(data.renew_minutes);
    else {
        var panel = document.querySelector(".deployment-actions");
        if (panel && panel.dataset.renewMinutes) setRenewLabel(panel.dataset.renewMinutes);
    }

    var expires = document.createElement("span");
    expires.textContent = formatExpiry(data.expires_at);
    alert.append(expires, document.createElement("br"));
    renderConnectionInfo(data.connection, alert);

    if (data.status === "provisioning" || data.instance_status === "provisioning") {
        var note = document.createElement("small");
        note.className = "text-muted d-block";
        note.textContent = tr("starting");
        alert.appendChild(note);
    }
}

function showError(message) {
    setAlert(trServerError(message) || tr("unknown"), true);
    hideChallengeUpdate();
    toggleChallengeCreate();
}

var provisioningPoll = null;
//: Challenge whose data is currently painted into the shared modal DOM.
//: CTFd reuses one modal element for every challenge, so a panel left over
//: from the previously opened challenge would otherwise keep showing its
//: connection details (and stealing the next request's response).
var displayedChallengeId = null;

function cancelProvisioningPoll() {
    if (provisioningPoll) {
        clearTimeout(provisioningPoll);
        provisioningPoll = null;
    }
}

function scheduleProvisioningPoll(challenge_id) {
    cancelProvisioningPoll();
    provisioningPoll = setTimeout(function () {
        provisioningPoll = null;
        view_container_info(challenge_id);
    }, 5000);
}

function resetPanelFor(challenge_id) {
    displayedChallengeId = challenge_id;
    cancelProvisioningPoll();
    setAlert("");                 // drop the previous challenge's connection info
    resetTerminateButton();
    hideChallengeUpdate();
    toggleChallengeCreate();
}

function view_container_info(challenge_id) {
    // The panel in the DOM may belong to a different challenge; never let it
    // keep showing that challenge's host/port while this request is in flight.
    if (displayedChallengeId !== null && displayedChallengeId !== challenge_id) {
        resetPanelFor(challenge_id);
    }

    displayedChallengeId = challenge_id;
    resetAlert();

    fetch("/api/v1/containers/info/" + challenge_id, {
        method: "GET",
        headers: {
            "Accept": "application/json",
            "CSRF-Token": init.csrfNonce
        }
    })
        .then(function (response) { return response.json(); })
        .then(function (data) {
            // A response for a challenge the player has already navigated away
            // from must never be painted.
            if (displayedChallengeId !== challenge_id || panelChallengeId() !== challenge_id) return;

            if (data.error) {
                showError(data.error);
                return;
            }
            if (data.status === "not_found") {
                setAlert(tr("none"));
                hideChallengeUpdate();
                toggleChallengeCreate();
                return;
            }
            if (data.status === "running" || data.status === "provisioning") {
                applyInstancePayload(data);
                hideChallengeCreate();
                toggleChallengeUpdate();
                if (data.status === "provisioning") {
                    scheduleProvisioningPoll(challenge_id);
                }
                return;
            }
            showError(data.error || tr("unknown_status", { s: data.status }));
        })
        .catch(function (error) {
            console.error("[Container] Fetch error:", error);
            if (displayedChallengeId === challenge_id) {
                showError(tr("err_info"));
            }
        })
        .finally(function () {
            if (displayedChallengeId === challenge_id) enableButtons();
        });
}

function container_request(challenge_id) {
    resetAlert();

    fetch("/api/v1/containers/request", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "CSRF-Token": init.csrfNonce
        },
        body: JSON.stringify({ challenge_id: challenge_id })
    })
        .then(function (response) { return response.json(); })
        .then(function (data) {
            if (data.error) {
                showError(data.error);
                return;
            }
            applyInstancePayload(data);
            hideChallengeCreate();
            toggleChallengeUpdate();
            if (data.status === "created" || data.status === "provisioning") {
                scheduleProvisioningPoll(challenge_id);
            }
        })
        .catch(function (error) {
            console.error("[Container] Request error:", error);
            showError(tr("err_request"));
        })
        .finally(enableButtons);
}

function container_renew(challenge_id) {
    resetAlert();

    fetch("/api/v1/containers/renew", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "CSRF-Token": init.csrfNonce
        },
        body: JSON.stringify({ challenge_id: challenge_id })
    })
        .then(function (response) { return response.json(); })
        .then(function (data) {
            if (data.error) {
                showError(data.error);
                return;
            }
            view_container_info(challenge_id);
        })
        .catch(function (error) {
            console.error("[Container] Renew error:", error);
            showError(tr("err_renew"));
        })
        .finally(enableButtons);
}

function container_terminate(challenge_id) {
    // Two-step inline confirmation: no browser confirm() dialog, and no
    // dependency on the theme's bundled (non-global) Bootstrap Modal.
    var button = el("terminate-chal");
    if (!button) return;

    if (button.dataset.confirming !== "1") {
        beginTerminateConfirm(button);
        return;
    }

    endTerminateConfirm(button);
    container_stop(challenge_id);
}

function container_stop(challenge_id) {
    resetAlert();

    fetch("/api/v1/containers/stop", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "CSRF-Token": init.csrfNonce
        },
        body: JSON.stringify({ challenge_id: challenge_id })
    })
        .then(function (response) { return response.json(); })
        .then(function (data) {
            if (data.error) {
                showError(data.error);
                return;
            }
            setAlert(tr("terminated"));
            hideChallengeUpdate();
            toggleChallengeCreate();
        })
        .catch(function (error) {
            console.error("[Container] Stop error:", error);
            showError(tr("err_stop"));
        })
        .finally(enableButtons);
}

function panelChallengeId() {
    var panel = document.querySelector(".deployment-actions");
    if (!panel) return null;
    var id = parseInt(panel.getAttribute("data-challenge-id"), 10);
    return isNaN(id) ? null : id;
}

// CTFd runs this script again on every challenge it opens, *before* the theme
// paints the new view, and some themes (Alpine x-html) paint it a tick after
// postRender. Until then the page still holds the previous challenge's panel,
// so wait for the panel of this challenge instead of using whatever is there.
function initContainerPanel(challengeId) {
    var attempts = 0;
    (function tryInit() {
        if (panelChallengeId() === challengeId) {
            view_container_info(challengeId);
            return;
        }
        attempts += 1;
        if (attempts < 25) setTimeout(tryInit, 200); // ~5s
    })();
}

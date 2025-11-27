const API_BASE = "http://127.0.0.1:5000/api";

function switchTab(tabName) {
  document.querySelectorAll(".tabs button").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab").forEach(sec => {
    sec.classList.toggle("active", sec.id === "tab-" + tabName);
  });
}

document.querySelectorAll(".tabs button").forEach(btn => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

async function loadPublicWallboard() {
  try {
    const res = await fetch(API_BASE + "/public/wallboard");
    const data = await res.json();
    const tbody = document.querySelector("#public-table tbody");
    tbody.innerHTML = "";
    data.items.forEach(item => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${item.date}</td>
        <td>${item.start}</td>
        <td>${item.end}</td>
        <td>${item.unit_name}</td>
        <td>${item.member_display}</td>
        <td>${item.override_first_out ? item.override_first_out : ""}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error("Failed to load wallboard", e);
  }
}

async function loadMemberList() {
  try {
    const res = await fetch(API_BASE + "/member/list");
    const members = await res.json();
    const select = document.querySelector("#member-select");
    select.innerHTML = "";
    members.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = `${m.first_name} ${m.last_name} (${m.member_number})`;
      select.appendChild(opt);
    });
    if (members.length > 0) {
      loadMemberSchedule(members[0].id);
    }
    select.addEventListener("change", () => {
      loadMemberSchedule(select.value);
    });
  } catch (e) {
    console.error("Failed to load member list", e);
  }
}

async function loadMemberSchedule(memberId) {
  try {
    const res = await fetch(API_BASE + "/member/" + memberId + "/schedule");
    const data = await res.json();
    const infoDiv = document.querySelector("#member-info");
    if (data.error) {
      infoDiv.textContent = data.error;
      return;
    }
    infoDiv.innerHTML = `
      <strong>${data.member.display}</strong><br>
      Position: ${data.member.position_type} |
      Expected hours: ${data.member.expected_min_hours}–${data.member.expected_max_hours}<br>
      Points balance: ${data.member.points_balance}
    `;
    const tbody = document.querySelector("#member-table tbody");
    tbody.innerHTML = "";
    data.shifts.forEach(s => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${s.date}</td>
        <td>${s.start}</td>
        <td>${s.end}</td>
        <td>${s.unit_id}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error("Failed to load member schedule", e);
  }
}

async function loadManagerCoverage() {
  try {
    const res = await fetch(API_BASE + "/manager/coverage");
    const data = await res.json();
    const tbody = document.querySelector("#manager-table tbody");
    tbody.innerHTML = "";
    data.rows.forEach(row => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${row.date}</td>
        <td>${row.start}</td>
        <td>${row.end}</td>
        <td>${row.unit_name}</td>
        <td>${row.assigned.join(", ")}</td>
        <td>${row.override_first_out ? row.override_first_out : ""}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error("Failed to load manager coverage", e);
  }
}

async function saveOverride() {
  const shiftId = document.querySelector("#override-shift-id").value.trim();
  const unitId = document.querySelector("#override-unit-id").value.trim();
  const status = document.querySelector("#override-status");
  if (!shiftId) {
    status.textContent = "Shift ID is required.";
    return;
  }
  try {
    const res = await fetch(API_BASE + "/manager/override_first_out", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        shift_id: shiftId,
        unit_id: unitId || null
      })
    });
    const data = await res.json();
    if (data.status === "ok") {
      status.textContent = "Override saved.";
      loadManagerCoverage();
      loadPublicWallboard();
    } else {
      status.textContent = "Error: " + (data.error || "unknown");
    }
  } catch (e) {
    console.error("Failed to save override", e);
    status.textContent = "Failed to save override.";
  }
}

document.querySelector("#override-save").addEventListener("click", saveOverride);

async function loadAdminSettings() {
  try {
    const res = await fetch(API_BASE + "/admin/settings");
    const data = await res.json();
    const container = document.querySelector("#admin-settings");
    container.innerHTML = "";

    const schedToggle = document.createElement("div");
    schedToggle.innerHTML = `
      <label>
        <input type="checkbox" id="admin-self-scheduling" ${data.self_scheduling_enabled ? "checked" : ""}>
        Self-scheduling enabled (core behavior)
      </label>
    `;
    container.appendChild(schedToggle);

    const rotationDiv = document.createElement("div");
    rotationDiv.innerHTML = `
      <p>Rotation order (comma-separated unit IDs):</p>
      <input type="text" id="admin-rotation" value="${data.rotation_order.join(",")}">
    `;
    container.appendChild(rotationDiv);

    const patterns = ["public", "member", "manager", "admin"];
    patterns.forEach(key => {
      const tmpl = data.display_templates[key];
      const div = document.createElement("div");
      div.innerHTML = `
        <h4>${key.charAt(0).toUpperCase() + key.slice(1)} display template</h4>
        <label>Pattern:
          <select data-role="pattern" data-key="${key}">
            <option value="INITIALS_NUMBER">INITIALS_NUMBER (XXX ####)</option>
            <option value="INITIALS">INITIALS (XXX)</option>
            <option value="NUMBER">NUMBER (####)</option>
            <option value="FIRST_LAST_NUMBER">FIRST_LAST_NUMBER (First Last ####)</option>
            <option value="FIRST_NUMBER">FIRST_NUMBER (First ####)</option>
            <option value="LAST_NUMBER">LAST_NUMBER (Last ####)</option>
            <option value="FIRST">FIRST</option>
            <option value="LAST">LAST</option>
          </select>
        </label>
        <label>
          <input type="checkbox" data-role="badges" data-key="${key}" ${tmpl.show_badges ? "checked" : ""}>
          Show badges (ALS / EMT / Driver)
        </label>
      `;
      container.appendChild(div);
      const select = div.querySelector("select[data-role='pattern']");
      select.value = tmpl.pattern;
    });
  } catch (e) {
    console.error("Failed to load admin settings", e);
  }
}

async function saveAdminSettings() {
  const status = document.querySelector("#admin-status");
  try {
    const selfScheduling = document.querySelector("#admin-self-scheduling").checked;
    const rotationStr = document.querySelector("#admin-rotation").value.trim();
    const rotation = rotationStr ? rotationStr.split(",").map(s => s.trim()).filter(Boolean) : [];

    const payload = {
      self_scheduling_enabled: selfScheduling,
      rotation_order: rotation,
      display_templates: {}
    };

    document.querySelectorAll("select[data-role='pattern']").forEach(sel => {
      const key = sel.dataset.key;
      if (!payload.display_templates[key]) {
        payload.display_templates[key] = {};
      }
      payload.display_templates[key].pattern = sel.value;
    });
    document.querySelectorAll("input[data-role='badges']").forEach(chk => {
      const key = chk.dataset.key;
      if (!payload.display_templates[key]) {
        payload.display_templates[key] = {};
      }
      payload.display_templates[key].show_badges = chk.checked;
    });

    const res = await fetch(API_BASE + "/admin/settings", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.status === "ok") {
      status.textContent = "Settings saved.";
      loadPublicWallboard();
      loadManagerCoverage();
    } else {
      status.textContent = "Error saving settings.";
    }
  } catch (e) {
    console.error("Failed to save admin settings", e);
    status.textContent = "Failed to save settings.";
  }
}

document.querySelector("#admin-save").addEventListener("click", saveAdminSettings);

// Initial load
loadPublicWallboard();
loadMemberList();
loadManagerCoverage();
loadAdminSettings();

// Main Application State & Controller

const appState = {
  faculty: null,
  classrooms: [],
  selectedCourse: null,
  assignments: [],
  selectedAssignment: null,
  rubric: null,
  evaluations: [],
  selectedStudent: null,
  activeFilter: "ALL",
  searchQuery: "",
  excelInfo: null,
  excelPreview: {
    currentType: "master",
    data: null,
    activeSheetIndex: 0,
    searchQuery: ""
  },
  isProcessing: false
};

// --- Initialization ---
document.addEventListener("DOMContentLoaded", async () => {
  await loadFaculty();
  await loadClassrooms();
  setupGlobalListeners();
  await restoreRouteFromUrl(true);
});

async function loadFaculty() {
  try {
    appState.faculty = await API.getFaculty();
    const rawName = appState.faculty.name || "Faculty";
    const cleanName = rawName.split("|")[0].trim();

    const nameEl = document.getElementById("faculty-name");
    if (nameEl) nameEl.textContent = cleanName;

    const emailEl = document.getElementById("faculty-email");
    if (emailEl) emailEl.textContent = appState.faculty.email || "";

    const avatarEl = document.getElementById("faculty-avatar");
    if (avatarEl) {
      const initials = cleanName
        .split(" ")
        .filter(Boolean)
        .slice(0, 2)
        .map(w => w[0].toUpperCase())
        .join("") || "F";
      avatarEl.textContent = initials;
    }

    const badge = document.getElementById("google-status-badge");
    const dot = document.getElementById("google-status-dot");
    if (badge) {
      if (appState.faculty.is_connected_google) {
        badge.className = "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-3xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200";
        badge.innerHTML = `<span class="w-1.5 h-1.5 bg-emerald-500 rounded-full"></span>Connected`;
        if (dot) dot.className = "absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full bg-emerald-500 ring-2 ring-white";
      } else {
        badge.className = "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-3xs font-semibold bg-amber-50 text-amber-700 border border-amber-200";
        badge.innerHTML = `<span class="w-1.5 h-1.5 bg-amber-500 rounded-full"></span>Sign In`;
        if (dot) dot.className = "absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full bg-amber-500 ring-2 ring-white";
      }
    }

    // Check if returning from Google OAuth redirect
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get("auth") === "google_success") {
      showToast(`Signed in to Google as ${urlParams.get("email") || appState.faculty.email}!`, "success");
      window.history.replaceState({ view: "classrooms", courseId: null, assignmentId: null }, document.title, window.location.pathname);
    } else if (!window.history.state) {
      window.history.replaceState({ view: "classrooms", courseId: null, assignmentId: null }, document.title, window.location.pathname + window.location.search);
    }
  } catch (err) {
    console.error("Failed to load faculty:", err);
  }
}

async function loadClassrooms() {
  try {
    showLoading(true);
    const [data, stats] = await Promise.all([
      API.getClassrooms(),
      API.getDashboardStats().catch(() => null)
    ]);
    appState.classrooms = data.courses || [];
    appState.dashboardStats = stats;

    if (stats) {
      document.getElementById("global-stat-courses").textContent = stats.total_classrooms;
      document.getElementById("global-stat-students").textContent = stats.total_students;
      document.getElementById("global-stat-assignments").textContent = stats.total_assignments;
      document.getElementById("global-stat-evaluated").textContent = stats.total_evaluated;
      document.getElementById("global-stat-approved").textContent = stats.total_approved;
    }

    renderClassroomsGrid();
    renderClassroomDropdown();
  } catch (err) {
    showToast("Error loading classrooms: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

function setupGlobalListeners() {
  // Listen for browser Back/Forward navigation
  window.addEventListener("popstate", async () => {
    await restoreRouteFromUrl(false);
  });

  // Classroom Selector in Header
  document.getElementById("header-course-select").addEventListener("change", async (e) => {
    const courseId = e.target.value;
    if (courseId) {
      await selectClassroom(courseId);
    } else {
      navigateTo("classrooms");
    }
  });

  // Search in student results
  document.getElementById("student-search")?.addEventListener("input", (e) => {
    appState.searchQuery = e.target.value.toLowerCase();
    renderEvaluationsTable();
  });
}

// --- Navigation, Routing & History ---
function buildUrl(viewName) {
  if (viewName === "classrooms" || !appState.selectedCourse) {
    return window.location.pathname;
  }
  const params = new URLSearchParams();
  params.set("course", appState.selectedCourse.id);
  if (appState.selectedAssignment && viewName !== "assignments") {
    params.set("assignment", appState.selectedAssignment.id);
    params.set("view", viewName);
  }
  return `${window.location.pathname}?${params.toString()}`;
}

let isRestoringRoute = false;
async function restoreRouteFromUrl(isInitialLoad = false) {
  if (isRestoringRoute) return;
  isRestoringRoute = true;
  try {
    const params = new URLSearchParams(window.location.search);
    const courseId = params.get("course");
    const assignmentId = params.get("assignment");
    const viewName = params.get("view");

    // Case 1: Root / Classrooms list
    if (!courseId) {
      appState.selectedCourse = null;
      appState.selectedAssignment = null;
      navigateTo("classrooms", { pushHistory: false });
      return;
    }

    // Case 2: Specific classroom selected
    if (!appState.selectedCourse || appState.selectedCourse.id !== courseId) {
      await selectClassroom(courseId, { pushHistory: false, skipNavigation: true });
    }

    // If no assignment in URL, stay on assignments list
    if (!assignmentId) {
      appState.selectedAssignment = null;
      navigateTo("assignments", { pushHistory: false });
      return;
    }

    // Case 3: Specific assignment selected
    if (!appState.selectedAssignment || appState.selectedAssignment.id !== assignmentId) {
      appState.selectedAssignment = (appState.assignments || []).find(a => a.id === assignmentId)
        || await API.getAssignmentDetail(courseId, assignmentId);
    }

    if (viewName === "rubric") {
      await loadRubricView({ pushHistory: false });
    } else if (viewName === "excel") {
      await loadExcelView({ pushHistory: false });
    } else if (viewName === "publish") {
      loadPublishView({ pushHistory: false });
    } else {
      if (appState.selectedAssignment && appState.selectedAssignment.evaluated_submissions > 0) {
        await loadEvaluationsView({ pushHistory: false });
      } else {
        await loadRubricView({ pushHistory: false });
      }
    }
  } catch (err) {
    console.error("Routing error:", err);
    navigateTo("classrooms", { pushHistory: false });
  } finally {
    isRestoringRoute = false;
  }
}

function updateBreadcrumbs(items) {
  const container = document.getElementById("breadcrumbs-container");
  container.innerHTML = "";
  items.forEach((item, index) => {
    const isLast = index === items.length - 1;
    const span = document.createElement("span");
    span.className = isLast ? "font-semibold text-slate-800" : "text-slate-500 hover:text-slate-700 cursor-pointer";
    span.textContent = item.label;
    if (!isLast && item.action) {
      span.onclick = item.action;
    }
    container.appendChild(span);

    if (!isLast) {
      const sep = document.createElement("span");
      sep.className = "text-slate-300 mx-2";
      sep.textContent = "/";
      container.appendChild(sep);
    }
  });
}

function navigateTo(viewName, options = { pushHistory: true }) {
  const views = ["view-classrooms", "view-assignments", "view-rubric", "view-evaluating", "view-results", "view-excel", "view-publish"];
  views.forEach(v => {
    const el = document.getElementById(v);
    if (el) el.classList.add("hidden");
  });

  const target = document.getElementById(`view-${viewName}`);
  if (target) target.classList.remove("hidden");

  // Scroll to top
  window.scrollTo({ top: 0, behavior: "instant" });

  // Update breadcrumb state based on view
  if (viewName === "classrooms") {
    updateBreadcrumbs([{ label: "My Classrooms" }]);
    const select = document.getElementById("header-course-select");
    if (select) select.value = "";
  } else if (viewName === "assignments" && appState.selectedCourse) {
    updateBreadcrumbs([
      { label: "My Classrooms", action: () => navigateTo("classrooms") },
      { label: `${appState.selectedCourse.name} (${appState.selectedCourse.section})` }
    ]);
  } else if (appState.selectedAssignment && appState.selectedCourse) {
    updateBreadcrumbs([
      { label: "My Classrooms", action: () => navigateTo("classrooms") },
      { label: `${appState.selectedCourse.name} (${appState.selectedCourse.section})`, action: () => navigateTo("assignments") },
      { label: appState.selectedAssignment.title, action: () => openAssignment(appState.selectedAssignment.id) },
      { label: viewName.charAt(0).toUpperCase() + viewName.slice(1) }
    ]);
  }

  // Manage URL & Browser History
  const push = options && options.pushHistory !== undefined ? options.pushHistory : true;
  if (push) {
    const targetUrl = buildUrl(viewName);
    const currentFullUrl = window.location.pathname + window.location.search;
    if (currentFullUrl !== targetUrl) {
      const stateObj = {
        view: viewName,
        courseId: appState.selectedCourse ? appState.selectedCourse.id : null,
        assignmentId: appState.selectedAssignment ? appState.selectedAssignment.id : null
      };
      window.history.pushState(stateObj, document.title, targetUrl);
    }
  }
}

// --- Classrooms View ---
function renderClassroomsGrid() {
  const grid = document.getElementById("classrooms-grid");
  grid.innerHTML = "";

  if (appState.classrooms.length === 0) {
    grid.innerHTML = `<div class="col-span-2 text-center py-12 text-slate-500">No classrooms found.</div>`;
    return;
  }

  appState.classrooms.forEach(course => {
    const courseSummary = appState.dashboardStats?.classrooms?.find(c => c.course_id === course.id);
    const evalCount = courseSummary ? courseSummary.evaluated_count : 0;
    const appCount = courseSummary ? courseSummary.approved_count : 0;
    const wbFilename = course.excel_workbook_path ? course.excel_workbook_path.split('/').pop() : `${course.name.toLowerCase().replace(/[^a-z0-9]/g, '_')}_marks_record.xlsx`;

    const card = document.createElement("div");
    card.className = "bg-white rounded-xl shadow-xs border border-slate-200 hover:border-blue-400 hover:shadow-md transition-all duration-200 p-6 flex flex-col justify-between space-y-4";
    card.innerHTML = `
      <div>
        <div class="flex items-start justify-between mb-3">
          <div class="flex items-center gap-2">
            <span class="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
              ${course.section}
            </span>
            <span class="text-xs text-emerald-600 font-medium flex items-center">
              <span class="w-2 h-2 rounded-full bg-emerald-500 mr-1.5"></span>${course.status}
            </span>
          </div>
          <span class="text-xs text-slate-400 font-mono">${course.id}</span>
        </div>
        <h3 class="text-lg font-bold text-slate-800 mb-1">${course.name}</h3>
        <p class="text-xs text-slate-500 mb-4 line-clamp-2">${course.description || "No description provided."}</p>
        
        <div class="grid grid-cols-2 gap-3 py-3 border-y border-slate-100 text-xs text-slate-600 mb-4">
          <div class="flex items-center gap-2">
            <span class="w-7 h-7 rounded-lg bg-slate-100 text-slate-700 font-bold flex items-center justify-center text-xs">${course.enrolled_count}</span>
            <div>
              <div class="font-semibold text-slate-800">Students</div>
              <div class="text-2xs text-slate-400">Isolated Roster</div>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <span class="w-7 h-7 rounded-lg bg-blue-50 text-blue-700 font-bold flex items-center justify-center text-xs">${course.assignments_count}</span>
            <div>
              <div class="font-semibold text-slate-800">Assignments</div>
              <div class="text-2xs text-slate-400">Classroom Scoped</div>
            </div>
          </div>
          <div class="col-span-2 flex items-center justify-between text-2xs pt-1 text-slate-500">
            <span>Evaluated: <strong class="text-slate-700">${evalCount}</strong></span>
            <span>Approved: <strong class="text-emerald-700">${appCount}</strong></span>
            <span>Room: ${course.room || "Campus Hall"}</span>
          </div>
        </div>

        <!-- Dedicated Classroom Workbook Section -->
        <div class="p-3 bg-slate-50 rounded-lg border border-slate-200 flex items-center justify-between text-xs">
          <div class="flex items-center gap-2 truncate">
            <svg class="w-4 h-4 text-emerald-600 shrink-0" fill="currentColor" viewBox="0 0 20 20"><path d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 2v2h8V6H6zm0 4v2h8v-2H6zm0 4v2h5v-2H6z"/></svg>
            <div class="truncate">
              <span class="font-bold text-slate-800 block text-2xs uppercase tracking-wider">Dedicated Workbook:</span>
              <span class="font-mono text-2xs text-slate-600 truncate block">${wbFilename}</span>
            </div>
          </div>
          <div class="flex items-center gap-1.5 shrink-0">
            <button onclick="viewClassroomWorkbook('${course.id}', event)" class="px-2.5 py-1 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-300 rounded text-2xs font-bold transition flex items-center gap-1">
              <svg class="w-3 h-3 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
              View
            </button>
            <a href="${API.downloadClassroomWorkbookUrl(course.id)}" target="_blank" onclick="event.stopPropagation();" class="px-2.5 py-1 bg-white hover:bg-slate-100 text-slate-700 border border-slate-300 rounded text-2xs font-bold transition flex items-center gap-1">
              <svg class="w-3 h-3 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
              Download
            </a>
          </div>
        </div>
      </div>

      <div class="flex items-center justify-end pt-2">
        <button onclick="selectClassroom('${course.id}')" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-lg shadow-xs transition flex items-center gap-1.5">
          <span>Open Classroom Workspace</span>
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
        </button>
      </div>
    `;
    grid.appendChild(card);
  });
}

function renderClassroomDropdown() {
  const select = document.getElementById("header-course-select");
  select.innerHTML = '<option value="">Switch Classroom...</option>';
  appState.classrooms.forEach(c => {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = `${c.name} (${c.section})`;
    select.appendChild(opt);
  });
}

async function selectClassroom(courseId, options = { pushHistory: true, skipNavigation: false }) {
  showLoading(true);
  try {
    appState.selectedCourse = appState.classrooms.find(c => c.id === courseId) || await API.getClassroom(courseId);
    const select = document.getElementById("header-course-select");
    if (select) select.value = courseId;
    
    // Fetch dedicated workbook info
    const wbInfo = await API.getClassroomWorkbookInfo(courseId).catch(() => null);
    const wbLink = document.getElementById("btn-download-course-wb");
    if (wbLink) wbLink.href = API.downloadClassroomWorkbookUrl(courseId);

    const pathBadge = document.getElementById("classroom-wb-path-badge");
    if (pathBadge && wbInfo) {
      pathBadge.textContent = wbInfo.path || "Pending Export Initialization";
    }
    const sheetsBadge = document.getElementById("classroom-wb-sheets-badge");
    if (sheetsBadge && wbInfo) {
      sheetsBadge.textContent = (wbInfo.sheets && wbInfo.sheets.length > 0) ? wbInfo.sheets.join(" | ") : "Consolidated Marks";
    }

    // Scoped assignments load
    appState.assignments = await API.getAssignments(courseId);
    renderAssignmentsList();

    const push = options && options.pushHistory !== undefined ? options.pushHistory : true;
    const skip = options && options.skipNavigation;
    if (!skip) {
      navigateTo("assignments", { pushHistory: push });
    }
  } catch (err) {
    showToast("Failed to load classroom: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

// --- Assignments View ---
function renderAssignmentsList() {
  document.getElementById("selected-course-title").textContent = appState.selectedCourse.name;
  document.getElementById("selected-course-meta").textContent = `Section: ${appState.selectedCourse.section} | Enrolled: ${appState.selectedCourse.enrolled_count} Students | Course ID: ${appState.selectedCourse.id}`;

  const tableBody = document.getElementById("assignments-table-body");
  tableBody.innerHTML = "";

  if (appState.assignments.length === 0) {
    tableBody.innerHTML = `<tr><td colspan="5" class="text-center py-8 text-slate-500">No assignments created for this classroom.</td></tr>`;
    return;
  }

  // Sort assignments naturally (Lab-1, Lab-2, ..., Lab-9)
  appState.assignments.sort((a, b) => {
    const parseNum = (title) => {
      const match = (title || "").match(/(lab|assignment|proj|quiz)[\s_-]*(\d+)/i);
      return match ? parseInt(match[2], 10) : 999;
    };
    return parseNum(a.title) - parseNum(b.title);
  });

  appState.assignments.forEach(assign => {
    const row = document.createElement("tr");
    row.className = "hover:bg-slate-50 border-b border-slate-100 transition";

    let statusBadge = `<span class="px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-600">Pending</span>`;
    if (assign.status === "EVALUATED") {
      statusBadge = `<span class="px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">Evaluated</span>`;
    } else if (assign.status === "APPROVED") {
      statusBadge = `<span class="px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-800">Approved</span>`;
    } else if (assign.status === "PUBLISHED") {
      statusBadge = `<span class="px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800">Published</span>`;
    }

    const actionText = assign.evaluated_submissions > 0 ? "Review & Marks" : "Configure & Evaluate";
    const actionColor = assign.evaluated_submissions > 0 ? "bg-emerald-600 hover:bg-emerald-700" : "bg-blue-600 hover:bg-blue-700";

    row.innerHTML = `
      <td class="py-4 px-4">
        <div class="font-bold text-slate-800">${assign.title}</div>
        <div class="text-xs text-slate-500 line-clamp-1">${assign.description || "No description"}</div>
      </td>
      <td class="py-4 px-4 text-center font-semibold text-slate-700">${assign.max_points} pts</td>
      <td class="py-4 px-4 text-center">
        <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-800">
          ${assign.total_submissions} / ${appState.selectedCourse.enrolled_count}
        </span>
      </td>
      <td class="py-4 px-4 text-center">${statusBadge}</td>
      <td class="py-4 px-4 text-right">
        <div class="flex items-center justify-end gap-2">
          ${assign.evaluated_submissions > 0 ? `
            <button onclick="openAndReEvaluate('${assign.id}')" title="Re-evaluate all submissions with latest approved rubric" class="px-2.5 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 text-xs font-semibold rounded-lg shadow-xs transition flex items-center gap-1">
              <svg class="w-3 h-3 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
              <span>Evaluate Again</span>
            </button>
          ` : ''}
          <button onclick="openAssignment('${assign.id}')" class="px-3.5 py-1.5 ${actionColor} text-white text-xs font-semibold rounded-lg shadow-sm transition">
            ${actionText}
          </button>
        </div>
      </td>
    `;
    tableBody.appendChild(row);
  });
}

async function openAndReEvaluate(assignmentId) {
  showLoading(true);
  try {
    appState.selectedAssignment = (appState.assignments || []).find(a => a.id === assignmentId) 
      || await API.getAssignmentDetail(appState.selectedCourse.id, assignmentId);

    // Verify rubric exists and is approved
    appState.rubric = await API.getRubric(appState.selectedCourse.id, assignmentId).catch(() => null);
    if (!appState.rubric || appState.rubric.status !== "APPROVED") {
      showToast("Please review and approve the marking rubric first.", "warning");
      await loadRubricView({ pushHistory: true });
      return;
    }

    await startEvaluationRun();
  } catch (err) {
    showToast("Error starting evaluation: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

async function triggerReEvaluation() {
  if (!appState.selectedAssignment) return;

  // Verify rubric exists and is approved
  if (!appState.rubric || appState.rubric.status !== "APPROVED") {
    appState.rubric = await API.getRubric(appState.selectedCourse.id, appState.selectedAssignment.id).catch(() => null);
  }

  if (!appState.rubric || appState.rubric.status !== "APPROVED") {
    showToast("Please review and approve the marking rubric before evaluating.", "warning");
    await loadRubricView({ pushHistory: true });
    return;
  }

  await startEvaluationRun();
}

async function openAssignment(assignmentId, options = { pushHistory: true }) {
  showLoading(true);
  try {
    appState.selectedAssignment = (appState.assignments || []).find(a => a.id === assignmentId) 
      || await API.getAssignmentDetail(appState.selectedCourse.id, assignmentId);

    const push = options && options.pushHistory !== undefined ? options.pushHistory : true;
    const targetView = options ? options.targetView : null;

    if (targetView === "rubric") {
      await loadRubricView({ pushHistory: push });
    } else if (targetView === "excel") {
      await loadExcelView({ pushHistory: push });
    } else if (targetView === "publish") {
      loadPublishView({ pushHistory: push });
    } else {
      // Check if already evaluated
      if (appState.selectedAssignment.evaluated_submissions > 0) {
        await loadEvaluationsView({ pushHistory: push });
      } else {
        await loadRubricView({ pushHistory: push });
      }
    }
  } catch (err) {
    showToast("Error opening assignment: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

// --- Rubric View ---
function autoResizeGuidanceTextarea() {
  const el = document.getElementById("rubric-guidance-input");
  if (!el) return;
  el.style.height = "auto";
  el.style.height = Math.max(92, Math.min(el.scrollHeight + 6, 320)) + "px";
}

function toggleGuidanceTemplates() {
  const container = document.getElementById("guidance-templates-container");
  if (!container) return;
  container.classList.toggle("hidden");
}

function setGuidanceTemplate(templateType) {
  const guidanceInput = document.getElementById("rubric-guidance-input");
  if (!guidanceInput) return;
  if (templateType === "arithmetic_binary") {
    guidanceInput.value = "The student is expected to submit a PDF or word file or code files that shows that he/she has executed the arithmetic operation and converting the decimal to binary with IDE code and terminal output screenshots.";
  } else if (templateType === "screenshots_pdf") {
    guidanceInput.value = "The student is expected to submit a PDF or word document containing screenshots of program source code and terminal execution outputs with problem headings.";
  } else if (templateType === "flowchart_code_output") {
    guidanceInput.value = "The student is expected to provide an algorithm, flowchart diagram, implementation code, and visual execution output proof.";
  } else if (templateType === "direct_code") {
    guidanceInput.value = "The student is expected to submit working C / C++ / Python source code files with comments, error handling, and compiler verification.";
  }
  autoResizeGuidanceTextarea();
}

async function loadRubricView(options = { pushHistory: true }) {
  const titleEl = document.getElementById("rubric-assign-title");
  if (titleEl) titleEl.textContent = appState.selectedAssignment.title;
  const descEl = document.getElementById("rubric-assign-desc");
  if (descEl) descEl.textContent = appState.selectedAssignment.description || "";
  const maxEl = document.getElementById("rubric-assign-max");
  if (maxEl) maxEl.textContent = `${appState.selectedAssignment.max_points} Points`;

  // Fetch existing rubric
  appState.rubric = await API.getRubric(appState.selectedCourse.id, appState.selectedAssignment.id);

  // Sync faculty expectations input
  const guidanceInput = document.getElementById("rubric-guidance-input");
  if (guidanceInput) {
    if (appState.rubric && appState.rubric.custom_guidance) {
      guidanceInput.value = appState.rubric.custom_guidance;
    } else if (!guidanceInput.value.trim()) {
      guidanceInput.value = "";
    }
    autoResizeGuidanceTextarea();
    if (!guidanceInput.dataset.hasResizeListener) {
      guidanceInput.addEventListener("input", autoResizeGuidanceTextarea);
      guidanceInput.dataset.hasResizeListener = "true";
    }
  }

  if (!appState.rubric) {
    // Propose generating
    document.getElementById("rubric-editor-container").classList.add("hidden");
    document.getElementById("rubric-empty-prompt").classList.remove("hidden");
  } else {
    document.getElementById("rubric-empty-prompt").classList.add("hidden");
    document.getElementById("rubric-editor-container").classList.remove("hidden");
    renderRubricCriteria();
  }

  const push = options && options.pushHistory !== undefined ? options.pushHistory : true;
  navigateTo("rubric", { pushHistory: push });
}

async function generateRubricAI() {
  const guidanceInput = document.getElementById("rubric-guidance-input");
  const customGuidance = guidanceInput ? guidanceInput.value.trim() : "";

  showLoading(true, "AI is analyzing assignment deliverables and formulating rubric criteria based on your expectations...");
  try {
    const criteria = await API.generateRubric(appState.selectedCourse.id, appState.selectedAssignment.id, customGuidance);
    
    // Save draft
    appState.rubric = await API.saveRubric(appState.selectedCourse.id, appState.selectedAssignment.id, {
      course_id: appState.selectedCourse.id,
      assignment_id: appState.selectedAssignment.id,
      criteria: criteria,
      total_max_marks: appState.selectedAssignment.max_points,
      late_penalty_percent: 30.0,
      custom_guidance: customGuidance
    });

    document.getElementById("rubric-empty-prompt").classList.add("hidden");
    document.getElementById("rubric-editor-container").classList.remove("hidden");
    renderRubricCriteria();
    showToast("Rubric successfully generated from your deliverable expectations!", "success");
  } catch (err) {
    showToast("Error generating rubric: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

function renderRubricCriteria() {
  const container = document.getElementById("rubric-criteria-list");
  if (!container || !appState.rubric || !appState.rubric.criteria) return;
  container.innerHTML = "";

  const isApproved = appState.rubric.status === "APPROVED";
  const statusBadge = document.getElementById("rubric-status-badge");
  const editBtn = document.getElementById("btn-edit-rubric");
  const approveBtn = document.getElementById("btn-approve-rubric");
  const startEvalBtn = document.getElementById("btn-start-eval");

  // Remove status badge element completely for clean header
  const statusBadge = document.getElementById("rubric-status-badge");
  if (statusBadge) {
    statusBadge.remove();
  }

  if (isApproved) {
    if (editBtn) editBtn.classList.remove("hidden");
    if (approveBtn) approveBtn.classList.add("hidden");
    if (startEvalBtn) startEvalBtn.classList.remove("hidden");
  } else {
    if (editBtn) editBtn.classList.add("hidden");
    if (approveBtn) approveBtn.classList.remove("hidden");
    if (startEvalBtn) startEvalBtn.classList.add("hidden");
  }

  const evalTypeMap = {
    code_execution: { label: "Code Execution", color: "bg-blue-50 text-blue-700 border-blue-200" },
    algorithm: { label: "Algorithm", color: "bg-purple-50 text-purple-700 border-purple-200" },
    diagram_flowchart: { label: "Flowchart / Diagram", color: "bg-emerald-50 text-emerald-700 border-emerald-200" },
    compliance: { label: "Quality & Compliance", color: "bg-slate-100 text-slate-700 border-slate-200" },
    descriptive: { label: "Descriptive", color: "bg-amber-50 text-amber-700 border-amber-200" }
  };

  appState.rubric.criteria.forEach((crit, idx) => {
    const typeMeta = evalTypeMap[crit.evaluation_type] || { label: crit.evaluation_type, color: "bg-slate-100 text-slate-700 border-slate-200" };
    const item = document.createElement("div");
    item.className = "p-4.5 bg-white border border-slate-200/90 hover:border-slate-300 rounded-xl transition shadow-2xs flex flex-col md:flex-row md:items-center justify-between gap-4";
    item.innerHTML = `
      <div class="flex-1 min-w-0">
        <div class="flex flex-wrap items-center gap-2 mb-1.5">
          <span class="w-6 h-6 rounded-md bg-blue-50 text-blue-700 text-xs font-bold flex items-center justify-center shrink-0 border border-blue-100/80">${idx + 1}</span>
          <h4 class="font-bold text-slate-800 text-sm tracking-tight">${crit.name}</h4>
          <span class="text-3xs font-semibold px-2 py-0.5 rounded-full border ${typeMeta.color}">${typeMeta.label}</span>
        </div>
        <p class="text-xs text-slate-500 pl-8 leading-relaxed">${crit.description}</p>
      </div>
      <div class="flex items-center gap-2 shrink-0 pl-8 md:pl-0">
        <label class="text-xs text-slate-400 font-medium">Max Marks:</label>
        <div class="flex items-center">
          <input type="number" step="any" min="0" max="100" id="criterion-mark-${crit.id}" value="${crit.max_marks}" ${isApproved ? "disabled" : ""} 
            oninput="updateCriterionMarks('${crit.id}', this.value)"
            class="w-20 px-2.5 py-1.5 text-sm font-bold text-slate-800 bg-slate-50 hover:bg-white border border-slate-200 rounded-lg text-right pr-2 focus:bg-white focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 focus:outline-none transition ${isApproved ? "opacity-75 cursor-not-allowed bg-slate-100" : ""}">
          <span class="text-xs font-semibold text-slate-400 ml-1.5">pts</span>
        </div>
      </div>
    `;
    container.appendChild(item);
  });

  updateTotalRubricCalc();
}

function updateTotalRubricCalc() {
  if (!appState.rubric || !appState.rubric.criteria) return;
  const currentTotal = appState.rubric.criteria.reduce((sum, c) => sum + (parseFloat(c.max_marks) || 0), 0);
  const rounded = Math.round(currentTotal * 10) / 10;
  const targetMax = appState.rubric.total_max_marks || (appState.selectedAssignment ? appState.selectedAssignment.max_points : 100);
  const totalCalcEl = document.getElementById("rubric-total-calc");
  if (totalCalcEl) {
    totalCalcEl.textContent = `${rounded} / ${targetMax} Points`;
    if (Math.abs(rounded - targetMax) > 0.5) {
      totalCalcEl.className = "text-sm font-bold text-amber-600";
    } else {
      totalCalcEl.className = "text-sm font-bold text-slate-800";
    }
  }
}

function updateCriterionMarks(critId, val) {
  const num = parseFloat(val) || 0;
  const crit = appState.rubric.criteria.find(c => c.id === critId);
  if (crit) {
    crit.max_marks = num;
    updateTotalRubricCalc();
  }
}

function editRubric() {
  if (!appState.rubric) return;
  appState.rubric.status = "DRAFT";
  renderRubricCriteria();
}

async function approveRubric() {
  showLoading(true, "Saving and approving rubric with your customized marks...");
  try {
    // Collect all input values directly from DOM to ensure 100% freshness
    if (appState.rubric && appState.rubric.criteria) {
      appState.rubric.criteria.forEach(crit => {
        const inputEl = document.getElementById(`criterion-mark-${crit.id}`);
        if (inputEl) {
          crit.max_marks = parseFloat(inputEl.value) || 0;
        }
      });
    }

    const currentTotal = appState.rubric.criteria.reduce((s, c) => s + (parseFloat(c.max_marks) || 0), 0);
    const roundedTotal = Math.round(currentTotal * 10) / 10;
    const targetMax = appState.selectedAssignment ? appState.selectedAssignment.max_points : roundedTotal;

    const guidanceInput = document.getElementById("rubric-guidance-input");
    const customGuidance = guidanceInput ? guidanceInput.value.trim() : (appState.rubric ? appState.rubric.custom_guidance : "");

    const payload = {
      course_id: appState.selectedCourse.id,
      assignment_id: appState.selectedAssignment.id,
      criteria: appState.rubric.criteria,
      total_max_marks: targetMax,
      late_penalty_percent: appState.rubric.late_penalty_percent || 30.0,
      custom_guidance: customGuidance
    };

    // Save customized criteria in DB first
    await API.saveRubric(appState.selectedCourse.id, appState.selectedAssignment.id, payload);

    // Approve rubric with the customized criteria
    appState.rubric = await API.approveRubric(appState.selectedCourse.id, appState.selectedAssignment.id, payload);

    renderRubricCriteria();
    showToast(`Rubric approved with your customized marks (${roundedTotal} / ${targetMax} pts)! You can now start automated evaluation.`, "success");
  } catch (err) {
    showToast("Failed to approve rubric: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

// --- Evaluation Progress & Execution ---
async function startEvaluationRun() {
  navigateTo("evaluating", { pushHistory: false });
  document.getElementById("eval-course-name").textContent = appState.selectedCourse.name;
  document.getElementById("eval-assign-name").textContent = appState.selectedAssignment.title;

  const progressBar = document.getElementById("eval-progress-bar");
  const progressText = document.getElementById("eval-progress-text");
  const statusDetail = document.getElementById("eval-status-detail");

  progressBar.style.width = "10%";
  progressText.textContent = "10%";
  statusDetail.textContent = "Loading authorized student submissions from database...";

  try {
    // Step animation
    setTimeout(() => {
      progressBar.style.width = "40%";
      progressText.textContent = "40%";
      statusDetail.textContent = "Extracting PDF, DOCX, and C source code deliverables...";
    }, 400);

    setTimeout(() => {
      progressBar.style.width = "70%";
      progressText.textContent = "70%";
      statusDetail.textContent = "Performing isolated compilation & local LLM rubric evaluation...";
    }, 900);

    const res = await API.startEvaluation(appState.selectedCourse.id, appState.selectedAssignment.id);

    progressBar.style.width = "100%";
    progressText.textContent = "100%";
    statusDetail.textContent = "Consolidating results and applying late penalties...";

    setTimeout(async () => {
      showToast(res.message, "success");
      await loadEvaluationsView();
    }, 600);
  } catch (err) {
    showToast("Evaluation error: " + err.message, "error");
    navigateTo("rubric");
  }
}

// --- Evaluation Results View ---
async function loadEvaluationsView(options = { pushHistory: true }) {
  showLoading(true);
  try {
    appState.evaluations = await API.getEvaluations(appState.selectedCourse.id, appState.selectedAssignment.id);
    document.getElementById("results-assign-title").textContent = appState.selectedAssignment.title;
    document.getElementById("results-course-meta").textContent = `${appState.selectedCourse.name} (${appState.selectedCourse.section})`;
    
    updateResultsStats();
    renderEvaluationsTable();
    const push = options && options.pushHistory !== undefined ? options.pushHistory : true;
    navigateTo("results", { pushHistory: push });
  } catch (err) {
    showToast("Failed to load evaluations: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

function updateResultsStats() {
  const evals = appState.evaluations;
  const total = evals.length;
  const avg = total > 0 ? (evals.reduce((sum, e) => sum + (e.faculty_adjusted_score !== null ? e.faculty_adjusted_score : e.final_score), 0) / total).toFixed(1) : 0;
  const approved = evals.filter(e => e.faculty_approved).length;
  const late = evals.filter(e => e.flags.includes("LATE")).length;
  const wrong = evals.filter(e => e.flags.includes("WRONG_PDF")).length;
  const uncertain = evals.filter(e => e.flags.includes("UNCERTAIN")).length;

  document.getElementById("stat-total-students").textContent = total;
  document.getElementById("stat-avg-score").textContent = `${avg} / ${appState.selectedAssignment.max_points}`;
  document.getElementById("stat-approved-count").textContent = `${approved} / ${total}`;
  document.getElementById("stat-irregular-count").textContent = late + wrong + uncertain;
}

function setResultsFilter(filterName) {
  appState.activeFilter = filterName;
  document.querySelectorAll(".filter-btn").forEach(btn => {
    btn.classList.remove("bg-blue-600", "text-white");
    btn.classList.add("bg-white", "text-slate-600");
  });
  const activeBtn = document.getElementById(`filter-btn-${filterName.toLowerCase()}`);
  if (activeBtn) {
    activeBtn.classList.remove("bg-white", "text-slate-600");
    activeBtn.classList.add("bg-blue-600", "text-white");
  }
  renderEvaluationsTable();
}

function renderEvaluationsTable() {
  const tbody = document.getElementById("evaluations-table-body");
  tbody.innerHTML = "";

  let list = appState.evaluations;

  // Filter
  if (appState.activeFilter === "MISSING") {
    list = list.filter(e => e.flags.includes("MISSING") || (e.faculty_remarks && e.faculty_remarks.toLowerCase().includes("missing")));
  } else if (appState.activeFilter === "UNCERTAIN") {
    list = list.filter(e => e.flags.includes("UNCERTAIN"));
  } else if (appState.activeFilter === "LATE") {
    list = list.filter(e => e.flags.includes("LATE"));
  } else if (appState.activeFilter === "WRONG_PDF") {
    list = list.filter(e => e.flags.includes("WRONG_PDF"));
  } else if (appState.activeFilter === "INCOMPLETE") {
    list = list.filter(e => e.flags.includes("INCOMPLETE"));
  } else if (appState.activeFilter === "APPROVED") {
    list = list.filter(e => e.faculty_approved);
  }

  // Search
  if (appState.searchQuery) {
    list = list.filter(e => 
      e.student_name.toLowerCase().includes(appState.searchQuery) ||
      e.student_id.toLowerCase().includes(appState.searchQuery)
    );
  }

  if (list.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-slate-500">No records matching the selected filter.</td></tr>`;
    return;
  }

  list.forEach(item => {
    const tr = document.createElement("tr");
    tr.className = `border-b border-slate-100 hover:bg-slate-50 transition cursor-pointer ${item.flags.includes("WRONG_PDF") ? "bg-red-50/40" : ""}`;
    
    // Effective score
    const scoreVal = item.faculty_adjusted_score !== null ? item.faculty_adjusted_score : item.final_score;
    const isOverridden = item.faculty_adjusted_score !== null;

    // Badges
    let flagBadges = "";
    if (item.flags.includes("MISSING") || (item.faculty_remarks && item.faculty_remarks.toLowerCase().includes("missing"))) {
      flagBadges += `<span class="badge-flag bg-red-100 text-red-800 border border-red-300 font-bold mr-1">Missing</span>`;
    }
    if (item.flags.includes("WRONG_PDF")) flagBadges += `<span class="badge-flag badge-wrong mr-1">Wrong PDF</span>`;
    if (item.flags.includes("LATE")) flagBadges += `<span class="badge-flag badge-late mr-1">Late</span>`;
    if (item.flags.includes("INCOMPLETE")) flagBadges += `<span class="badge-flag badge-incomplete mr-1">Incomplete</span>`;
    if (item.flags.includes("UNCERTAIN")) flagBadges += `<span class="badge-flag badge-uncertain mr-1">Review</span>`;
    if (!flagBadges) flagBadges = `<span class="text-xs text-slate-400">Normal</span>`;

    const approvedIcon = item.faculty_approved
      ? `<span class="inline-flex items-center text-xs font-semibold text-emerald-700 bg-emerald-100 px-2.5 py-0.5 rounded-full"><svg class="w-3.5 h-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>Approved</span>`
      : `<span class="inline-flex items-center text-xs font-medium text-amber-700 bg-amber-100 px-2.5 py-0.5 rounded-full">Pending</span>`;

    // Student Work direct button
    const hasAttachments = item.attachments && item.attachments.length > 0;
    let viewWorkBtn = "";
    if (hasAttachments) {
      const attCount = item.attachments.length;
      const countLabel = attCount > 1 ? ` (${attCount})` : "";
      const tooltip = attCount === 1
        ? `Open ${item.attachments[0].filename} directly in Google Drive`
        : `View ${attCount} files submitted by ${item.student_name}`;

      viewWorkBtn = `
        <button onclick="viewStudentWork('${item.student_id}', event)" class="px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 hover:text-indigo-800 text-xs font-semibold rounded border border-indigo-200 transition inline-flex items-center gap-1 shadow-2xs shrink-0" title="${tooltip}">
          <svg class="w-3.5 h-3.5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/>
          </svg>
          <span>View Work${countLabel}</span>
        </button>
      `;
    } else {
      viewWorkBtn = `
        <button disabled class="px-2.5 py-1 bg-slate-50 text-slate-400 text-xs font-medium rounded border border-slate-200 cursor-not-allowed inline-flex items-center gap-1 opacity-60 shrink-0" title="No submission attachments found for this student">
          <svg class="w-3.5 h-3.5 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"/>
          </svg>
          <span>No Work</span>
        </button>
      `;
    }

    tr.innerHTML = `
      <td class="py-3 px-4 font-mono text-xs text-slate-600">${item.student_id}</td>
      <td class="py-3 px-4 font-semibold text-slate-800">${item.student_name}</td>
      <td class="py-3 px-4 text-center">
        <span class="font-bold text-slate-800 ${isOverridden ? 'text-blue-600' : ''}">${scoreVal}</span>
        ${isOverridden ? '<span class="text-xs text-blue-500 block font-normal">(adjusted)</span>' : ''}
      </td>
      <td class="py-3 px-4 text-center text-xs text-slate-500">${item.late_penalty > 0 ? `-${item.late_penalty}` : '-'}</td>
      <td class="py-3 px-4">${flagBadges}</td>
      <td class="py-3 px-4 text-center">${approvedIcon}</td>
      <td class="py-3 px-4 text-right whitespace-nowrap">
        <div class="inline-flex items-center gap-2 justify-end">
          ${viewWorkBtn}
          <button onclick="openStudentModal('${item.student_id}')" class="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium rounded border border-slate-200 transition shrink-0">
            Inspect & Adjust
          </button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// --- File Type Badge Helper ---
function getFileTypeBadge(filename, fileType) {
  const ext = (filename ? filename.split('.').pop() : '').toLowerCase();
  if (ext === 'pdf' || fileType === 'PDF') {
    return `<span class="px-1.5 py-0.5 bg-red-100 text-red-700 text-3xs font-bold rounded uppercase">PDF</span>`;
  } else if (['docx', 'doc'].includes(ext) || fileType === 'DOCX') {
    return `<span class="px-1.5 py-0.5 bg-blue-100 text-blue-700 text-3xs font-bold rounded uppercase">DOCX</span>`;
  } else if (['c', 'cpp', 'h', 'py', 'java', 'js'].includes(ext) || fileType === 'CODE') {
    return `<span class="px-1.5 py-0.5 bg-emerald-100 text-emerald-700 text-3xs font-bold rounded uppercase">CODE</span>`;
  } else if (['png', 'jpg', 'jpeg', 'webp', 'bmp'].includes(ext) || fileType === 'IMAGE') {
    return `<span class="px-1.5 py-0.5 bg-amber-100 text-amber-700 text-3xs font-bold rounded uppercase">IMAGE</span>`;
  }
  return `<span class="px-1.5 py-0.5 bg-slate-100 text-slate-700 text-3xs font-bold rounded uppercase">${ext || 'FILE'}</span>`;
}

// --- View Student Work Handler ---
function viewStudentWork(studentId, event) {
  if (event) event.stopPropagation();
  const item = appState.evaluations.find(e => e.student_id === studentId);
  if (!item || !item.attachments || item.attachments.length === 0) {
    showToast("No submitted files found for this student.", "warning");
    return;
  }

  if (item.attachments.length === 1) {
    const att = item.attachments[0];
    const url = att.link || (att.file_id ? `https://drive.google.com/file/d/${att.file_id}/view?usp=drivesdk` : `/api/classrooms/${appState.selectedCourse.id}/assignments/${appState.selectedAssignment.id}/submissions/${studentId}/work`);
    if (url) {
      window.open(url, "_blank", "noopener,noreferrer");
    } else {
      showToast("No direct link available for this file.", "warning");
    }
    return;
  }

  // Multiple files -> open popup selector
  openMultiWorkModal(item);
}

function openMultiWorkModal(item) {
  const modal = document.getElementById("multi-work-modal");
  document.getElementById("work-modal-title").textContent = item.student_name;
  document.getElementById("work-modal-subtitle").textContent = `${item.student_id} • ${item.attachments.length} files submitted`;

  const listEl = document.getElementById("work-modal-file-list");
  listEl.innerHTML = "";

  item.attachments.forEach(a => {
    const link = a.link || (a.file_id ? `https://drive.google.com/file/d/${a.file_id}/view?usp=drivesdk` : `/api/classrooms/${appState.selectedCourse.id}/assignments/${appState.selectedAssignment.id}/submissions/${item.student_id}/work`);
    const badge = getFileTypeBadge(a.filename, a.file_type);
    const row = document.createElement("div");
    row.className = "flex items-center justify-between p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs hover:bg-slate-100 transition";
    row.innerHTML = `
      <div class="flex items-center gap-2 min-w-0 pr-2">
        ${badge}
        <span class="font-medium text-slate-800 truncate" title="${a.filename}">${a.filename}</span>
      </div>
      <a href="${link}" target="_blank" rel="noopener noreferrer" class="px-3 py-1 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded text-xs transition inline-flex items-center gap-1 shrink-0">
        <span>Open in Drive</span>
        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
      </a>
    `;
    listEl.appendChild(row);
  });

  const openAllBtn = document.getElementById("work-modal-open-all-btn");
  openAllBtn.onclick = () => {
    item.attachments.forEach(a => {
      const link = a.link || (a.file_id ? `https://drive.google.com/file/d/${a.file_id}/view?usp=drivesdk` : null);
      if (link) window.open(link, "_blank", "noopener,noreferrer");
    });
  };

  modal.classList.remove("hidden");
}

function closeMultiWorkModal() {
  const modal = document.getElementById("multi-work-modal");
  if (modal) modal.classList.add("hidden");
}

// --- Student Detail Inspection Modal ---
async function openStudentModal(studentId) {
  showLoading(true);
  try {
    appState.selectedStudent = await API.getStudentEvaluation(appState.selectedCourse.id, appState.selectedAssignment.id, studentId);
    const s = appState.selectedStudent;

    document.getElementById("modal-student-name").textContent = s.student_name;
    document.getElementById("modal-student-id").textContent = s.student_id;
    document.getElementById("modal-score-input").value = s.faculty_adjusted_score !== null ? s.faculty_adjusted_score : s.final_score;
    document.getElementById("modal-remarks-input").value = s.faculty_remarks || "";
    document.getElementById("modal-approve-checkbox").checked = s.faculty_approved;

    // Render student submitted work / attachments
    const attList = s.attachments || [];
    const attContainer = document.getElementById("modal-attachments-list");
    const countBadge = document.getElementById("modal-work-count-badge");
    if (attContainer && countBadge) {
      attContainer.innerHTML = "";
      if (attList.length === 0) {
        countBadge.textContent = "0 files";
        attContainer.innerHTML = `
          <div class="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center gap-2">
            <svg class="w-4 h-4 text-red-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
            <span>No submission files received (Missing submission or empty turn-in).</span>
          </div>
        `;
      } else {
        countBadge.textContent = `${attList.length} file${attList.length > 1 ? 's' : ''}`;
        attList.forEach(a => {
          const link = a.link || (a.file_id ? `https://drive.google.com/file/d/${a.file_id}/view?usp=drivesdk` : `/api/classrooms/${appState.selectedCourse.id}/assignments/${appState.selectedAssignment.id}/submissions/${s.student_id}/work`);
          const fileTypeBadge = getFileTypeBadge(a.filename, a.file_type);
          const itemEl = document.createElement("div");
          itemEl.className = "flex items-center justify-between p-2.5 bg-white border border-slate-200 rounded-lg text-xs hover:border-indigo-300 transition";
          itemEl.innerHTML = `
            <div class="flex items-center gap-2 min-w-0 pr-2">
              ${fileTypeBadge}
              <span class="font-medium text-slate-800 truncate" title="${a.filename}">${a.filename}</span>
            </div>
            <a href="${link}" target="_blank" rel="noopener noreferrer" class="px-3 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 hover:text-indigo-800 font-semibold rounded border border-indigo-200 transition inline-flex items-center gap-1 shrink-0">
              <span>Open in Drive</span>
              <svg class="w-3 h-3 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
            </a>
          `;
          attContainer.appendChild(itemEl);
        });
      }
    }

    // Render criteria breakdown
    const critContainer = document.getElementById("modal-criteria-breakdown");
    critContainer.innerHTML = "";
    s.criteria_breakdown.forEach(c => {
      const row = document.createElement("div");
      row.className = "p-3 bg-white border border-slate-200 rounded-lg text-xs space-y-1";
      row.innerHTML = `
        <div class="flex items-center justify-between font-semibold">
          <span class="text-slate-800">${c.criterion_name}</span>
          <span class="text-blue-700 font-bold">${c.awarded_marks} / ${c.max_marks} pts [${c.status}]</span>
        </div>
        <p class="text-slate-600">${c.explanation}</p>
        ${c.evidence ? `<div class="p-2 bg-slate-50 rounded border border-slate-100 text-slate-500 font-mono text-2xs truncate">Evidence: ${c.evidence}</div>` : ''}
      `;
      critContainer.appendChild(row);
    });

    // Overall feedback & code execution
    document.getElementById("modal-overall-feedback").textContent = s.overall_feedback;
    const codeBox = document.getElementById("modal-code-results");
    if (s.code_execution_results) {
      codeBox.classList.remove("hidden");
      document.getElementById("modal-code-status").textContent = s.code_execution_results.compilation_success 
        ? `Compiled successfully. Tests passed: ${s.code_execution_results.tests_passed}/${s.code_execution_results.tests_total}`
        : `Compilation error: ${s.code_execution_results.compilation_error}`;
    } else {
      codeBox.classList.add("hidden");
    }

    document.getElementById("student-modal").classList.remove("hidden");
  } catch (err) {
    showToast("Error loading student details: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

function closeStudentModal() {
  document.getElementById("student-modal").classList.add("hidden");
  appState.selectedStudent = null;
}

async function saveStudentAdjustment() {
  const s = appState.selectedStudent;
  if (!s) return;

  const scoreVal = parseFloat(document.getElementById("modal-score-input").value);
  const remarksVal = document.getElementById("modal-remarks-input").value.trim();
  const isApproved = document.getElementById("modal-approve-checkbox").checked;

  try {
    showLoading(true, "Saving faculty adjustments...");
    await API.adjustStudentEvaluation(appState.selectedCourse.id, appState.selectedAssignment.id, s.student_id, {
      faculty_adjusted_score: isNaN(scoreVal) ? null : scoreVal,
      faculty_remarks: remarksVal,
      faculty_approved: isApproved
    });

    closeStudentModal();
    await loadEvaluationsView();
    showToast("Grade adjustments saved successfully.", "success");
  } catch (err) {
    showToast("Failed to save adjustments: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

async function approveAllEvaluations() {
  if (!confirm("Are you sure you want to approve all evaluated marks for this assignment?")) return;

  try {
    showLoading(true, "Batch approving all student marks...");
    const res = await API.batchApprove(appState.selectedCourse.id, appState.selectedAssignment.id);
    await loadEvaluationsView();
    showToast(`Approved ${res.approved_count} student evaluations!`, "success");
  } catch (err) {
    showToast("Error approving evaluations: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

// --- Excel Reporting View ---
async function loadExcelView(options = { pushHistory: true }) {
  showLoading(true);
  try {
    appState.excelInfo = await API.getExcelColumns(appState.selectedCourse.id, appState.selectedAssignment.id);
    document.getElementById("excel-assign-title").textContent = appState.selectedAssignment.title;
    document.getElementById("excel-course-name").textContent = `${appState.selectedCourse.name} (${appState.selectedCourse.section})`;

    const select = document.getElementById("excel-target-column-select");
    select.innerHTML = "";

    appState.excelInfo.columns.forEach(col => {
      const opt = document.createElement("option");
      opt.value = col;
      opt.textContent = col;
      if (col === appState.excelInfo.suggested_column) {
        opt.selected = true;
      }
      select.appendChild(opt);
    });

    // Add option to create new column
    const newOpt = document.createElement("option");
    newOpt.value = appState.selectedAssignment.title;
    newOpt.textContent = `+ Create New Column: "${appState.selectedAssignment.title}"`;
    select.appendChild(newOpt);

    document.getElementById("excel-workbook-path-display").textContent = appState.excelInfo.workbook_path;
    const push = options && options.pushHistory !== undefined ? options.pushHistory : true;
    navigateTo("excel", { pushHistory: push });
  } catch (err) {
    showToast("Failed to load Excel configuration: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

async function executeExcelExport() {
  const targetCol = document.getElementById("excel-target-column-select").value;
  showLoading(true, `Consolidating marks into column "${targetCol}" and generating reports...`);

  try {
    const res = await API.exportExcel(appState.selectedCourse.id, appState.selectedAssignment.id, targetCol);
    document.getElementById("excel-export-success-box").classList.remove("hidden");
    document.getElementById("excel-output-master-path").textContent = res.versioned_master_workbook;
    document.getElementById("excel-output-detail-path").textContent = res.detail_report_path;
    document.getElementById("excel-updated-count").textContent = res.total_records_updated;
    showToast(res.message, "success");
  } catch (err) {
    showToast("Excel Export Failed: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

async function viewClassroomWorkbook(courseId, event) {
  if (event) {
    event.stopPropagation();
  }
  const course = appState.classrooms.find(c => c.id === courseId);
  if (course) {
    appState.selectedCourse = course;
  }
  await openExcelPreviewModal("master", courseId, null);
}

function downloadExcelReport(type) {
  const courseId = appState.selectedCourse?.id || appState.excelPreview?.courseId;
  const assignmentId = appState.selectedAssignment?.id || appState.excelPreview?.assignmentId;
  if (!courseId) {
    showToast("Classroom not selected.", "error");
    return;
  }
  if (!assignmentId || type === "master") {
    window.open(API.downloadClassroomWorkbookUrl(courseId), "_blank");
    return;
  }
  const url = `/api/classrooms/${courseId}/assignments/${assignmentId}/excel/download?file_type=${type}`;
  window.open(url, "_blank");
}

// --- Excel Preview & Spreadsheet Viewer Modal ---
async function openExcelPreviewModal(fileType = "master", explicitCourseId = null, explicitAssignmentId = null) {
  const targetCourseId = explicitCourseId || (appState.selectedCourse ? appState.selectedCourse.id : null);
  const targetAssignmentId = explicitAssignmentId !== undefined ? explicitAssignmentId : (appState.selectedAssignment ? appState.selectedAssignment.id : null);

  if (!targetCourseId) {
    showToast("Please select a classroom first.", "warning");
    return;
  }

  showLoading(true, `Loading ${fileType === "master" ? "Consolidated Workbook" : "Detailed Report"} preview...`);
  try {
    let data;
    if (targetAssignmentId) {
      data = await API.previewExcel(targetCourseId, targetAssignmentId, fileType);
    } else {
      data = await API.previewClassroomWorkbook(targetCourseId);
      fileType = "master";
    }

    appState.excelPreview = {
      courseId: targetCourseId,
      assignmentId: targetAssignmentId,
      currentType: fileType,
      data: data,
      activeSheetIndex: 0,
      searchQuery: ""
    };

    updateExcelPreviewUI();
    document.getElementById("excel-preview-search").value = "";
    document.getElementById("excel-preview-modal").classList.remove("hidden");
  } catch (err) {
    showToast("Failed to preview Excel: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

function updateExcelPreviewUI() {
  const p = appState.excelPreview;
  if (!p.data) return;

  const isMaster = p.currentType === "master";
  document.getElementById("excel-preview-modal-title").textContent = isMaster
    ? "Consolidated Master Workbook"
    : "Detailed Assignment Report";

  const pill = document.getElementById("excel-preview-type-pill");
  pill.textContent = isMaster ? "Master Workbook" : "Detailed Report";
  pill.className = isMaster
    ? "text-3xs font-bold uppercase px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 shrink-0"
    : "text-3xs font-bold uppercase px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 shrink-0";

  document.getElementById("excel-preview-filename").textContent = p.data.filename;

  // Update switcher tabs
  const masterBtn = document.getElementById("excel-tab-btn-master");
  const detailBtn = document.getElementById("excel-tab-btn-detail");
  if (!p.assignmentId) {
    detailBtn.classList.add("opacity-40", "cursor-not-allowed");
    detailBtn.title = "Detailed report is assignment-specific (open an assignment to view)";
    detailBtn.onclick = () => showToast("Open an assignment workspace to view its Detailed Evaluation Report.", "info");
    masterBtn.className = "px-2.5 py-1 rounded-md transition bg-emerald-600 text-white font-semibold";
    masterBtn.onclick = () => switchExcelPreviewType('master');
  } else {
    detailBtn.classList.remove("opacity-40", "cursor-not-allowed");
    detailBtn.title = "View detailed rubric criteria breakdown";
    detailBtn.onclick = () => switchExcelPreviewType('detail');
    masterBtn.onclick = () => switchExcelPreviewType('master');
    if (isMaster) {
      masterBtn.className = "px-2.5 py-1 rounded-md transition bg-emerald-600 text-white font-semibold";
      detailBtn.className = "px-2.5 py-1 rounded-md transition text-slate-600 hover:text-slate-900";
    } else {
      masterBtn.className = "px-2.5 py-1 rounded-md transition text-slate-600 hover:text-slate-900";
      detailBtn.className = "px-2.5 py-1 rounded-md transition bg-blue-600 text-white font-semibold";
    }
  }

  renderExcelSheetTabs();
  renderExcelPreviewTable();
}

async function switchExcelPreviewType(type) {
  if (appState.excelPreview.currentType === type && appState.excelPreview.data) {
    return;
  }
  const courseId = appState.excelPreview?.courseId || appState.selectedCourse?.id;
  const assignmentId = appState.excelPreview?.assignmentId || appState.selectedAssignment?.id;
  if (!assignmentId && type !== "master") {
    showToast("Detailed report is only available within an assignment.", "info");
    return;
  }
  await openExcelPreviewModal(type, courseId, assignmentId);
}

function renderExcelSheetTabs() {
  const container = document.getElementById("excel-preview-sheet-tabs-container");
  container.innerHTML = "";
  const sheets = appState.excelPreview.data.sheets || [];

  sheets.forEach((s, idx) => {
    const isActive = idx === appState.excelPreview.activeSheetIndex;
    const btn = document.createElement("button");
    btn.className = `px-3 py-1 rounded-md font-semibold text-xs transition flex items-center gap-1.5 whitespace-nowrap ${
      isActive
        ? "bg-white text-emerald-800 shadow-2xs border border-slate-200"
        : "text-slate-600 hover:bg-slate-200/60"
    }`;
    btn.innerHTML = `
      <svg class="w-3.5 h-3.5 ${isActive ? 'text-emerald-600' : 'text-slate-400'}" fill="currentColor" viewBox="0 0 20 20"><path d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 2v2h8V6H6zm0 4v2h8v-2H6zm0 4v2h5v-2H6z"/></svg>
      <span>${s.sheet_name}</span>
      <span class="text-3xs px-1.5 py-0.2 rounded-full ${isActive ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'}">${s.total_rows}</span>
    `;
    btn.onclick = () => {
      appState.excelPreview.activeSheetIndex = idx;
      renderExcelSheetTabs();
      renderExcelPreviewTable();
    };
    container.appendChild(btn);
  });
}

function filterExcelPreviewRows() {
  appState.excelPreview.searchQuery = (document.getElementById("excel-preview-search").value || "").trim().toLowerCase();
  renderExcelPreviewTable();
}

function renderExcelPreviewTable() {
  const p = appState.excelPreview;
  const thead = document.getElementById("excel-preview-thead");
  const tbody = document.getElementById("excel-preview-tbody");
  const emptyEl = document.getElementById("excel-preview-empty");
  thead.innerHTML = "";
  tbody.innerHTML = "";

  const sheets = (p.data && p.data.sheets) || [];
  if (sheets.length === 0) {
    emptyEl.textContent = "This workbook contains no data sheets.";
    emptyEl.classList.remove("hidden");
    return;
  }

  const sheet = sheets[p.activeSheetIndex] || sheets[0];
  const headers = sheet.headers || [];
  const rows = sheet.rows || [];

  // Build thead
  const trHead = document.createElement("tr");
  const thIdx = document.createElement("th");
  thIdx.className = "py-2.5 px-3 bg-slate-900 text-slate-300 font-mono text-3xs uppercase tracking-wider text-center w-12 border-r border-slate-700";
  thIdx.textContent = "#";
  trHead.appendChild(thIdx);

  headers.forEach(h => {
    const th = document.createElement("th");
    th.className = "py-2.5 px-3 bg-slate-800 text-slate-100 font-semibold text-xs border-r border-slate-700 whitespace-nowrap";
    th.textContent = h;
    trHead.appendChild(th);
  });
  thead.appendChild(trHead);

  // Filter rows
  const q = p.searchQuery;
  const filteredRows = q
    ? rows.filter(r => r.some(cell => String(cell).toLowerCase().includes(q)))
    : rows;

  document.getElementById("excel-preview-row-count").textContent = `${filteredRows.length} of ${rows.length} rows`;
  document.getElementById("excel-preview-col-count").textContent = `${headers.length} columns`;

  if (filteredRows.length === 0) {
    emptyEl.textContent = "No records matching the search query.";
    emptyEl.classList.remove("hidden");
    return;
  }
  emptyEl.classList.add("hidden");

  // Build tbody
  filteredRows.forEach((row, rIdx) => {
    const tr = document.createElement("tr");
    tr.className = `border-b border-slate-100 hover:bg-emerald-50/40 transition ${rIdx % 2 === 1 ? 'bg-slate-50/50' : 'bg-white'}`;

    // Row number cell
    const tdIdx = document.createElement("td");
    tdIdx.className = "py-2 px-3 font-mono text-3xs text-slate-400 bg-slate-100 text-center border-r border-slate-200 select-none";
    tdIdx.textContent = rIdx + 1;
    tr.appendChild(tdIdx);

    row.forEach((cellVal, cIdx) => {
      const td = document.createElement("td");
      td.className = "py-2 px-3 text-xs text-slate-700 border-r border-slate-100 whitespace-nowrap";
      
      const strVal = String(cellVal || "").trim();
      const colHeader = (headers[cIdx] || "").toLowerCase();

      // Formatting heuristics
      if (colHeader.includes("student id") || colHeader.includes("roll")) {
        td.className += " font-mono font-medium text-slate-600";
        td.textContent = strVal;
      } else if (colHeader.includes("name")) {
        td.className += " font-semibold text-slate-900";
        td.textContent = strVal;
      } else if (colHeader.includes("score") || colHeader.includes("marks") || colHeader.startsWith("lab-")) {
        td.className += " text-center font-bold";
        if (strVal === "0" || strVal === "0.0") {
          td.innerHTML = `<span class="text-slate-400 font-normal">0</span>`;
        } else if (!isNaN(parseFloat(strVal))) {
          td.innerHTML = `<span class="text-emerald-700">${strVal}</span>`;
        } else {
          td.textContent = strVal;
        }
      } else if (colHeader.includes("status")) {
        if (strVal.toLowerCase() === "approved") {
          td.innerHTML = `<span class="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-3xs font-bold">Approved</span>`;
        } else {
          td.innerHTML = `<span class="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-3xs font-medium">${strVal || 'Draft'}</span>`;
        }
      } else if (colHeader.includes("remarks")) {
        if (strVal.toLowerCase().includes("missing")) {
          td.innerHTML = `<span class="px-2 py-0.5 rounded-full bg-red-100 text-red-800 text-3xs font-bold mr-1">Missing</span>`;
        } else if (strVal.toLowerCase().includes("wrong")) {
          td.innerHTML = `<span class="px-2 py-0.5 rounded-full bg-red-100 text-red-700 text-3xs font-bold mr-1">Wrong PDF</span>`;
        } else if (strVal.toLowerCase().includes("late")) {
          td.innerHTML = `<span class="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-3xs font-semibold mr-1">Late</span>`;
        } else {
          td.textContent = strVal;
        }
      } else if (colHeader.includes("breakdown") || colHeader.includes("evidence") || colHeader.includes("feedback")) {
        td.className = "py-2 px-3 text-xs text-slate-600 border-r border-slate-100 max-w-xs truncate";
        td.title = strVal;
        td.textContent = strVal;
      } else {
        td.textContent = strVal;
      }

      tr.appendChild(td);
    });

    tbody.appendChild(tr);
  });
}

function downloadCurrentPreviewFile() {
  const p = appState.excelPreview;
  if (!p || !p.currentType) return;
  downloadExcelReport(p.currentType);
}

function closeExcelPreviewModal() {
  document.getElementById("excel-preview-modal").classList.add("hidden");
}

// --- Google Classroom Publishing View ---
function loadPublishView(options = { pushHistory: true }) {
  const approvedCount = appState.evaluations.filter(e => e.faculty_approved).length;
  document.getElementById("publish-assign-title").textContent = appState.selectedAssignment.title;
  document.getElementById("publish-course-name").textContent = `${appState.selectedCourse.name} (${appState.selectedCourse.section})`;
  document.getElementById("publish-ready-count").textContent = approvedCount;
  document.getElementById("publish-total-count").textContent = appState.evaluations.length;

  if (approvedCount === 0) {
    document.getElementById("publish-warning-alert").classList.remove("hidden");
    document.getElementById("btn-trigger-publish-modal").disabled = true;
  } else {
    document.getElementById("publish-warning-alert").classList.add("hidden");
    document.getElementById("btn-trigger-publish-modal").disabled = false;
  }

  const push = options && options.pushHistory !== undefined ? options.pushHistory : true;
  navigateTo("publish", { pushHistory: push });
}

function openPublishConfirmModal() {
  document.getElementById("publish-confirm-modal").classList.remove("hidden");
}

function closePublishConfirmModal() {
  document.getElementById("publish-confirm-modal").classList.add("hidden");
}

async function confirmAndPublish() {
  const returnSubs = document.getElementById("publish-return-checkbox").checked;
  closePublishConfirmModal();
  showLoading(true, "Publishing approved marks to Google Classroom...");

  try {
    const res = await API.publishGrades(appState.selectedCourse.id, appState.selectedAssignment.id, returnSubs);
    showToast(res.message, "success");
    document.getElementById("publish-result-box").classList.remove("hidden");
    document.getElementById("publish-result-msg").textContent = res.message;
    document.getElementById("publish-timestamp").textContent = res.timestamp;
  } catch (err) {
    showToast("Publishing Failed: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

// --- UI Utilities ---
function showLoading(show, message = "Loading data...") {
  const el = document.getElementById("loading-overlay");
  const msgEl = document.getElementById("loading-message");
  if (show) {
    msgEl.textContent = message;
    el.classList.remove("hidden");
  } else {
    el.classList.add("hidden");
  }
}

function showToast(message, type = "info") {
  const toast = document.createElement("div");
  const colors = {
    success: "bg-emerald-600 text-white",
    error: "bg-red-600 text-white",
    info: "bg-slate-800 text-white"
  };
  toast.className = `fixed bottom-5 right-5 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium transition-opacity duration-300 ${colors[type] || colors.info}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// --- Google Auth Modal & Live Sync ---
async function openGoogleAuthModal() {
  showLoading(true);
  try {
    const clientInfo = await API.getGoogleClientInfo();
    const faculty = await API.getFaculty();
    appState.faculty = faculty;

    document.getElementById("modal-client-id").textContent = clientInfo.client_id || "Not configured (credentials.json missing)";
    const statusEl = document.getElementById("modal-google-status");
    const connectedActions = document.getElementById("google-connected-actions");
    const loginAction = document.getElementById("google-login-action");
    const credForm = document.getElementById("credentials-setup-form");

    if (faculty.is_connected_google) {
      statusEl.className = "font-bold text-emerald-600";
      statusEl.textContent = `Connected (${faculty.email})`;
      document.getElementById("google-connected-email").textContent = `Active Account: ${faculty.email}`;
      connectedActions.classList.remove("hidden");
      loginAction.classList.add("hidden");
      credForm.classList.add("hidden");
    } else {
      connectedActions.classList.add("hidden");

      if (clientInfo.configured) {
        statusEl.className = "font-bold text-amber-600";
        statusEl.textContent = "Google Sign-In Required";
        loginAction.classList.remove("hidden");
        credForm.classList.add("hidden");
      } else {
        statusEl.className = "font-bold text-red-600";
        statusEl.textContent = "Configuration Required (Upload credentials.json)";
        loginAction.classList.add("hidden");
        credForm.classList.remove("hidden");
      }
    }

    document.getElementById("google-auth-modal").classList.remove("hidden");
  } catch (err) {
    showToast("Error loading Google connection info: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

function closeGoogleAuthModal() {
  document.getElementById("google-auth-modal").classList.add("hidden");
}

function toggleCredentialsForm() {
  const form = document.getElementById("credentials-setup-form");
  form.classList.toggle("hidden");
}

async function saveDirectClientSecrets() {
  const cid = document.getElementById("input-client-id").value.trim();
  const csecret = document.getElementById("input-client-secret").value.trim();
  if (!cid || !csecret) {
    showToast("Please enter both Client ID and Client Secret.", "error");
    return;
  }
  showLoading(true, "Saving credentials...");
  try {
    const payload = {
      client_id: cid,
      client_secret: csecret,
      redirect_uris: [
        "http://localhost:8000/api/auth/google/callback",
        "http://127.0.0.1:8000/api/auth/google/callback"
      ]
    };
    await API.saveCredentialsJson(payload);
    showToast("OAuth credentials saved! Redirecting to Google Login...", "success");
    window.location.href = "/api/auth/google/login";
  } catch (err) {
    showToast("Failed to save credentials: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

async function uploadCredentialsJson() {
  const fileInput = document.getElementById("input-credentials-file");
  if (!fileInput.files || fileInput.files.length === 0) {
    showToast("Please select your credentials.json file first.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  showLoading(true, "Saving credentials.json...");
  try {
    const res = await API.uploadCredentialsFile(formData);
    showToast(res.message, "success");
    await openGoogleAuthModal();
  } catch (err) {
    showToast("Failed to upload credentials: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

async function syncLiveClassrooms() {
  if (!appState.faculty || !appState.faculty.is_connected_google) {
    showToast("Please sign in with your Google account first to sync live courses.", "warning");
    await openGoogleAuthModal();
    return;
  }
  showLoading(true, "Connecting to Google Classroom API and synchronizing courses...");
  try {
    const res = await API.syncLiveGoogle();
    showToast(res.message || "Classrooms synchronized with Google Classroom!", "success");
    closeGoogleAuthModal();
    await loadClassrooms();
  } catch (err) {
    showToast("Live Sync Error: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

async function disconnectGoogleAccount() {
  if (!confirm("Are you sure you want to disconnect your Google account?")) return;
  showLoading(true, "Disconnecting Google account...");
  try {
    await API.disconnectGoogle();
    showToast("Google account disconnected.", "info");
    closeGoogleAuthModal();
    await loadFaculty();
    await loadClassrooms();
  } catch (err) {
    showToast("Error: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}


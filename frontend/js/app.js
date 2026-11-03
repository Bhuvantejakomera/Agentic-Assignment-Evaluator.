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
  isProcessing: false
};

// --- Initialization ---
document.addEventListener("DOMContentLoaded", async () => {
  await loadFaculty();
  await loadClassrooms();
  setupGlobalListeners();
});

async function loadFaculty() {
  try {
    appState.faculty = await API.getFaculty();
    document.getElementById("faculty-name").textContent = appState.faculty.name;
    document.getElementById("faculty-email").textContent = appState.faculty.email;
    const badge = document.getElementById("google-status-badge");
    if (appState.faculty.is_connected_google) {
      badge.className = "inline-flex items-center px-2.5 py-1 rounded-full text-2xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300 hover:bg-emerald-200 transition cursor-pointer";
      badge.innerHTML = `<span class="w-2 h-2 mr-1.5 bg-emerald-500 rounded-full"></span>Google Connected`;
    } else {
      badge.className = "inline-flex items-center px-2.5 py-1 rounded-full text-2xs font-semibold bg-slate-100 text-slate-700 border border-slate-300 hover:bg-slate-200 transition cursor-pointer";
      badge.innerHTML = `<span class="w-2 h-2 mr-1.5 bg-slate-400 rounded-full"></span>Connect Google`;
    }

    // Check if returning from Google OAuth redirect
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get("auth") === "google_success") {
      showToast(`Signed in to Google as ${urlParams.get("email") || appState.faculty.email}!`, "success");
      window.history.replaceState({}, document.title, window.location.pathname);
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

// --- Navigation & Breadcrumbs ---
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

function navigateTo(viewName) {
  const views = ["view-classrooms", "view-assignments", "view-rubric", "view-evaluating", "view-results", "view-excel", "view-publish"];
  views.forEach(v => {
    const el = document.getElementById(v);
    if (el) el.classList.add("hidden");
  });

  const target = document.getElementById(`view-${viewName}`);
  if (target) target.classList.remove("hidden");

  // Update breadcrumb state based on view
  if (viewName === "classrooms") {
    updateBreadcrumbs([{ label: "My Classrooms" }]);
    document.getElementById("header-course-select").value = "";
  } else if (viewName === "assignments") {
    updateBreadcrumbs([
      { label: "My Classrooms", action: () => navigateTo("classrooms") },
      { label: `${appState.selectedCourse.name} (${appState.selectedCourse.section})` }
    ]);
  } else if (appState.selectedAssignment) {
    updateBreadcrumbs([
      { label: "My Classrooms", action: () => navigateTo("classrooms") },
      { label: `${appState.selectedCourse.name} (${appState.selectedCourse.section})`, action: () => navigateTo("assignments") },
      { label: appState.selectedAssignment.title, action: () => navigateTo("rubric") },
      { label: viewName.charAt(0).toUpperCase() + viewName.slice(1) }
    ]);
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
          <a href="${API.downloadClassroomWorkbookUrl(course.id)}" target="_blank" onclick="event.stopPropagation();" class="px-2.5 py-1 bg-white hover:bg-slate-100 text-emerald-800 border border-emerald-300 rounded text-2xs font-bold transition shrink-0 flex items-center gap-1">
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
            Download
          </a>
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

async function selectClassroom(courseId) {
  showLoading(true);
  try {
    appState.selectedCourse = appState.classrooms.find(c => c.id === courseId) || await API.getClassroom(courseId);
    document.getElementById("header-course-select").value = courseId;
    
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
    navigateTo("assignments");
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
        <button onclick="openAssignment('${assign.id}')" class="px-3.5 py-1.5 ${actionColor} text-white text-xs font-semibold rounded-lg shadow-sm transition">
          ${actionText}
        </button>
      </td>
    `;
    tableBody.appendChild(row);
  });
}

async function openAssignment(assignmentId) {
  showLoading(true);
  try {
    appState.selectedAssignment = appState.assignments.find(a => a.id === assignmentId) 
      || await API.getAssignmentDetail(appState.selectedCourse.id, assignmentId);

    // Check if already evaluated
    if (appState.selectedAssignment.evaluated_submissions > 0) {
      await loadEvaluationsView();
    } else {
      await loadRubricView();
    }
  } catch (err) {
    showToast("Error opening assignment: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

// --- Rubric View ---
async function loadRubricView() {
  document.getElementById("rubric-assign-title").textContent = appState.selectedAssignment.title;
  document.getElementById("rubric-assign-desc").textContent = appState.selectedAssignment.description || "";
  document.getElementById("rubric-assign-max").textContent = `${appState.selectedAssignment.max_points} Points`;

  // Fetch existing rubric
  appState.rubric = await API.getRubric(appState.selectedCourse.id, appState.selectedAssignment.id);

  if (!appState.rubric) {
    // Propose generating
    document.getElementById("rubric-editor-container").classList.add("hidden");
    document.getElementById("rubric-empty-prompt").classList.remove("hidden");
  } else {
    document.getElementById("rubric-empty-prompt").classList.add("hidden");
    document.getElementById("rubric-editor-container").classList.remove("hidden");
    renderRubricCriteria();
  }

  navigateTo("rubric");
}

async function generateRubricAI() {
  showLoading(true, "AI is analyzing assignment deliverables and generating rubric criteria...");
  try {
    const criteria = await API.generateRubric(appState.selectedCourse.id, appState.selectedAssignment.id);
    
    // Save draft
    appState.rubric = await API.saveRubric(appState.selectedCourse.id, appState.selectedAssignment.id, {
      course_id: appState.selectedCourse.id,
      assignment_id: appState.selectedAssignment.id,
      criteria: criteria,
      total_max_marks: appState.selectedAssignment.max_points,
      late_penalty_percent: 20.0
    });

    document.getElementById("rubric-empty-prompt").classList.add("hidden");
    document.getElementById("rubric-editor-container").classList.remove("hidden");
    renderRubricCriteria();
    showToast("Rubric successfully generated by Local LLM!", "success");
  } catch (err) {
    showToast("Error generating rubric: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

function renderRubricCriteria() {
  const container = document.getElementById("rubric-criteria-list");
  container.innerHTML = "";

  const isApproved = appState.rubric.status === "APPROVED";
  const statusBadge = document.getElementById("rubric-status-badge");
  if (isApproved) {
    statusBadge.className = "px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-300";
    statusBadge.textContent = "APPROVED BY FACULTY";
    document.getElementById("btn-approve-rubric").classList.add("hidden");
    document.getElementById("btn-start-eval").classList.remove("hidden");
  } else {
    statusBadge.className = "px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300";
    statusBadge.textContent = "DRAFT (REQUIRES APPROVAL)";
    document.getElementById("btn-approve-rubric").classList.remove("hidden");
    document.getElementById("btn-start-eval").classList.add("hidden");
  }

  let totalMarks = 0;
  appState.rubric.criteria.forEach((crit, idx) => {
    totalMarks += crit.max_marks;
    const item = document.createElement("div");
    item.className = "p-4 bg-slate-50 border border-slate-200 rounded-lg flex flex-col md:flex-row md:items-center justify-between gap-4";
    item.innerHTML = `
      <div class="flex-1">
        <div class="flex items-center gap-2 mb-1">
          <span class="w-6 h-6 rounded-full bg-blue-100 text-blue-800 text-xs font-bold flex items-center justify-center">${idx + 1}</span>
          <h4 class="font-bold text-slate-800">${crit.name}</h4>
          <span class="text-xs px-2 py-0.5 rounded bg-slate-200 text-slate-700">${crit.evaluation_type}</span>
        </div>
        <p class="text-xs text-slate-600 pl-8">${crit.description}</p>
      </div>
      <div class="flex items-center gap-3 pl-8 md:pl-0">
        <label class="text-xs text-slate-500 font-medium">Max Marks:</label>
        <input type="number" min="1" max="100" value="${crit.max_marks}" ${isApproved ? "disabled" : ""} 
          onchange="updateCriterionMarks('${crit.id}', this.value)"
          class="w-20 px-2 py-1 text-sm font-bold text-slate-800 border border-slate-300 rounded focus:ring-1 focus:ring-blue-500">
      </div>
    `;
    container.appendChild(item);
  });

  document.getElementById("rubric-total-calc").textContent = `${totalMarks} / ${appState.rubric.total_max_marks} Points`;
}

function updateCriterionMarks(critId, val) {
  const num = parseFloat(val) || 0;
  const crit = appState.rubric.criteria.find(c => c.id === critId);
  if (crit) {
    crit.max_marks = num;
    renderRubricCriteria();
  }
}

async function approveRubric() {
  showLoading(true, "Saving and approving rubric...");
  try {
    appState.rubric = await API.approveRubric(appState.selectedCourse.id, appState.selectedAssignment.id);
    renderRubricCriteria();
    showToast("Rubric approved! You can now start automated evaluation.", "success");
  } catch (err) {
    showToast("Failed to approve rubric: " + err.message, "error");
  } finally {
    showLoading(false);
  }
}

// --- Evaluation Progress & Execution ---
async function startEvaluationRun() {
  navigateTo("evaluating");
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
async function loadEvaluationsView() {
  showLoading(true);
  try {
    appState.evaluations = await API.getEvaluations(appState.selectedCourse.id, appState.selectedAssignment.id);
    document.getElementById("results-assign-title").textContent = appState.selectedAssignment.title;
    document.getElementById("results-course-meta").textContent = `${appState.selectedCourse.name} (${appState.selectedCourse.section})`;
    
    updateResultsStats();
    renderEvaluationsTable();
    navigateTo("results");
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
  if (appState.activeFilter === "UNCERTAIN") {
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
    if (item.flags.includes("WRONG_PDF")) flagBadges += `<span class="badge-flag badge-wrong mr-1">Wrong PDF</span>`;
    if (item.flags.includes("LATE")) flagBadges += `<span class="badge-flag badge-late mr-1">Late</span>`;
    if (item.flags.includes("INCOMPLETE")) flagBadges += `<span class="badge-flag badge-incomplete mr-1">Incomplete</span>`;
    if (item.flags.includes("UNCERTAIN")) flagBadges += `<span class="badge-flag badge-uncertain mr-1">Review</span>`;
    if (!flagBadges) flagBadges = `<span class="text-xs text-slate-400">Normal</span>`;

    const approvedIcon = item.faculty_approved
      ? `<span class="inline-flex items-center text-xs font-semibold text-emerald-700 bg-emerald-100 px-2.5 py-0.5 rounded-full"><svg class="w-3.5 h-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>Approved</span>`
      : `<span class="inline-flex items-center text-xs font-medium text-amber-700 bg-amber-100 px-2.5 py-0.5 rounded-full">Pending</span>`;

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
      <td class="py-3 px-4 text-right">
        <button onclick="openStudentModal('${item.student_id}')" class="px-2.5 py-1 bg-slate-100 hover:bg-blue-50 hover:text-blue-700 text-slate-700 text-xs font-medium rounded border border-slate-200 transition">
          Inspect & Adjust
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
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
async function loadExcelView() {
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
    navigateTo("excel");
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

function downloadExcelReport(type) {
  const url = `/api/classrooms/${appState.selectedCourse.id}/assignments/${appState.selectedAssignment.id}/excel/download?file_type=${type}`;
  window.open(url, "_blank");
}

// --- Google Classroom Publishing View ---
function loadPublishView() {
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

  navigateTo("publish");
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
      statusEl.className = "font-bold text-amber-600";
      statusEl.textContent = "Not connected";
      connectedActions.classList.add("hidden");
      loginAction.classList.remove("hidden");
      if (!clientInfo.configured) {
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
  showLoading(true, "Connecting to Google Classroom API and synchronizing courses...");
  try {
    const res = await API.syncLiveGoogle();
    showToast(res.message, "success");
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


// Client API Service
const API_BASE = "";

async function parseErrorResponse(res, defaultMsg = "Request failed") {
  try {
    const err = await res.json();
    return err.detail || err.message || defaultMsg;
  } catch (_) {
    try {
      const text = await res.text();
      return text || res.statusText || defaultMsg;
    } catch (e) {
      return res.statusText || defaultMsg;
    }
  }
}

const API = {
  // Auth & Faculty
  async getFaculty() {
    const res = await fetch(`${API_BASE}/api/auth/faculty`);
    return res.json();
  },
  async getGoogleClientInfo() {
    const res = await fetch(`${API_BASE}/api/auth/google/client-info`);
    return res.json();
  },
  async uploadCredentialsFile(formData) {
    const res = await fetch(`${API_BASE}/api/auth/google/upload-credentials`, {
      method: "POST",
      body: formData
    });
    if (!res.ok) {
      const msg = await parseErrorResponse(res, "Failed to upload credentials.");
      throw new Error(msg);
    }
    return res.json();
  },
  async saveCredentialsJson(payload) {
    const res = await fetch(`${API_BASE}/api/auth/google/save-credentials`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const msg = await parseErrorResponse(res, "Failed to save credentials.");
      throw new Error(msg);
    }
    return res.json();
  },
  async syncLiveGoogle() {
    const res = await fetch(`${API_BASE}/api/auth/google/sync-live`, { method: "POST" });
    if (!res.ok) {
      const msg = await parseErrorResponse(res, "Failed to sync live Google Classroom.");
      throw new Error(msg);
    }
    return res.json();
  },
  async disconnectGoogle() {
    const res = await fetch(`${API_BASE}/api/auth/disconnect`, { method: "POST" });
    return res.json();
  },

  // Classrooms
  async getClassrooms() {
    const res = await fetch(`${API_BASE}/api/classrooms`);
    return res.json();
  },
  async getDashboardStats() {
    const res = await fetch(`${API_BASE}/api/classrooms/dashboard/stats`);
    return res.json();
  },
  async getClassroom(courseId) {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}`);
    return res.json();
  },
  async syncClassroom(courseId) {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/sync`, { method: "POST" });
    return res.json();
  },
  async getClassroomWorkbookInfo(courseId) {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/workbook/info`);
    return res.json();
  },
  downloadClassroomWorkbookUrl(courseId) {
    return `${API_BASE}/api/classrooms/${courseId}/workbook`;
  },
  async previewClassroomWorkbook(courseId) {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/workbook/preview`);
    if (!res.ok) {
      const msg = await parseErrorResponse(res, "Failed to load classroom workbook preview.");
      throw new Error(msg);
    }
    return res.json();
  },

  // Assignments
  async getAssignments(courseId) {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/assignments`);
    return res.json();
  },
  async getAssignmentDetail(courseId, assignmentId) {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}`);
    return res.json();
  },

  // Rubrics
  async getRubric(courseId, assignmentId) {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/rubric`);
    return res.json();
  },
  async generateRubric(courseId, assignmentId, customGuidance = "") {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/rubric/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ course_id: courseId, assignment_id: assignmentId, custom_guidance: customGuidance })
    });
    return res.json();
  },
  async saveRubric(courseId, assignmentId, rubricData) {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/rubric/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rubricData)
    });
    return res.json();
  },
  async approveRubric(courseId, assignmentId, rubricData = null) {
    const opts = { method: "POST" };
    if (rubricData) {
      opts.headers = { "Content-Type": "application/json" };
      opts.body = JSON.stringify(rubricData);
    }
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/rubric/approve`, opts);
    return res.json();
  },

  // Evaluation
  async startEvaluation(courseId, assignmentId) {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/evaluate`, {
      method: "POST"
    });
    if (!res.ok) {
      const msg = await parseErrorResponse(res, "Evaluation failed to start.");
      throw new Error(msg);
    }
    return res.json();
  },
  async getEvaluations(courseId, assignmentId) {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/evaluations`);
    return res.json();
  },
  async getStudentEvaluation(courseId, assignmentId, studentId) {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/evaluations/${studentId}`);
    return res.json();
  },
  async adjustStudentEvaluation(courseId, assignmentId, studentId, data) {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/evaluations/${studentId}/adjust`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    return res.json();
  },
  async batchApprove(courseId, assignmentId, studentIds = null) {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/batch-approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ course_id: courseId, assignment_id: assignmentId, student_ids: studentIds })
    });
    return res.json();
  },

  // Excel
  async getExcelColumns(courseId, assignmentId) {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/excel/columns`);
    return res.json();
  },
  async previewExcel(courseId, assignmentId, fileType = "master") {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/excel/preview?file_type=${fileType}`);
    if (!res.ok) {
      const msg = await parseErrorResponse(res, "Failed to load Excel preview.");
      throw new Error(msg);
    }
    return res.json();
  },
  async exportExcel(courseId, assignmentId, targetColumn = null) {
    const url = targetColumn 
      ? `${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/excel/export?target_column_name=${encodeURIComponent(targetColumn)}`
      : `${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/excel/export`;
    const res = await fetch(url, { method: "POST" });
    if (!res.ok) {
      const msg = await parseErrorResponse(res, "Failed to export Excel.");
      throw new Error(msg);
    }
    return res.json();
  },

  // Publishing
  async publishGrades(courseId, assignmentId, returnSubmissions = false) {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        course_id: courseId,
        assignment_id: assignmentId,
        return_submissions: returnSubmissions,
        faculty_confirmation: true
      })
    });
    if (!res.ok) {
      const msg = await parseErrorResponse(res, "Publishing failed.");
      throw new Error(msg);
    }
    return res.json();
  }
};


// Client API Service
const API_BASE = "";

const API = {
  // Auth & Faculty
  async getFaculty() {
    const res = await fetch(`${API_BASE}/api/auth/faculty`);
    return res.json();
  },
  async connectGoogle() {
    const res = await fetch(`${API_BASE}/api/auth/connect-google`, { method: "POST" });
    return res.json();
  },

  // Classrooms
  async getClassrooms() {
    const res = await fetch(`${API_BASE}/api/classrooms`);
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
  async approveRubric(courseId, assignmentId) {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/rubric/approve`, {
      method: "POST"
    });
    return res.json();
  },

  // Evaluation
  async startEvaluation(courseId, assignmentId) {
    const res = await fetch(`${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/evaluate`, {
      method: "POST"
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Evaluation failed to start.");
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
  async exportExcel(courseId, assignmentId, targetColumn = null) {
    const url = targetColumn 
      ? `${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/excel/export?target_column_name=${encodeURIComponent(targetColumn)}`
      : `${API_BASE}/api/classrooms/${courseId}/assignments/${assignmentId}/excel/export`;
    const res = await fetch(url, { method: "POST" });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to export Excel.");
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
      const err = await res.json();
      throw new Error(err.detail || "Publishing failed.");
    }
    return res.json();
  }
};

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";


export function getAccessToken() {
  return sessionStorage.getItem("access_token");
}


export function setAccessToken(token) {
  if (!token) {
    return;
  }

  sessionStorage.setItem("access_token", token);
}


export function clearAccessToken() {
  sessionStorage.removeItem("access_token");
}


const SELECTED_COMPANY_KEY = "selected_company";


// "*" is the development wildcard, not a real Tally company name.
export function getSelectedCompany() {
  const company = sessionStorage.getItem(SELECTED_COMPANY_KEY);

  return company && company !== "*" ? company : null;
}


export function setSelectedCompany(company) {
  if (company) {
    sessionStorage.setItem(SELECTED_COMPANY_KEY, company);
  } else {
    sessionStorage.removeItem(SELECTED_COMPANY_KEY);
  }
}


// Users assigned to several companies must name one on every report
// request, so the selected company is attached here once instead of
// in each page.
function withSelectedCompany(path) {
  const company = getSelectedCompany();

  if (!company || /[?&]company_name=/.test(path)) {
    return path;
  }

  const separator = path.includes("?") ? "&" : "?";

  return `${path}${separator}company_name=${encodeURIComponent(company)}`;
}


function buildHeaders(extraHeaders = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...extraHeaders,
  };

  const token = getAccessToken();

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return headers;
}


async function handleResponse(response) {
  let data;

  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const message =
      data?.detail ||
      data?.message ||
      "Something went wrong.";

    const error = new Error(message);
    error.status = response.status;

    throw error;
  }

  return data;
}


export async function apiGet(path, options = {}) {
  const { signal } = options;

  const response = await fetch(
    `${API_BASE_URL}${withSelectedCompany(path)}`,
    {
      method: "GET",
      headers: buildHeaders(),
      signal,
    }
  );

  return handleResponse(response);
}


export async function apiPost(path, body) {
  const response = await fetch(
    `${API_BASE_URL}${path}`,
    {
      method: "POST",
      headers: buildHeaders(),
      body: JSON.stringify(body),
    }
  );

  return handleResponse(response);
}

export async function apiPatch(path, body) {
  const response = await fetch(
    `${API_BASE_URL}${path}`,
    {
      method: "PATCH",
      headers: buildHeaders(),
      body: JSON.stringify(body),
    }
  );

  return handleResponse(response);
}

export async function apiDelete(path) {
  const response = await fetch(
    `${API_BASE_URL}${path}`,
    {
      method: "DELETE",
      headers: buildHeaders(),
    }
  );

  return handleResponse(response);
}

export async function downloadFile(path, filename = "download") {
  const response = await fetch(
    `${API_BASE_URL}${withSelectedCompany(path)}`,
    {
      method: "GET",
      headers: buildHeaders(),
    }
  );

  if (!response.ok) {
    let message = "Unable to download file.";

    try {
      const data = await response.json();
      message =
        data?.detail ||
        data?.message ||
        message;
    } catch {
      // Response may not be JSON.
    }

    const error = new Error(message);
    error.status = response.status;

    throw error;
  }

  const blob = await response.blob();

  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = filename;

  document.body.appendChild(link);
  link.click();
  link.remove();

  window.URL.revokeObjectURL(url);
}
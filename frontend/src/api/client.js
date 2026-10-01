const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL;

const CSRF_COOKIE_NAME =
  import.meta.env.VITE_CSRF_COOKIE_NAME;

const CSRF_HEADER_NAME =
  import.meta.env.VITE_CSRF_HEADER_NAME;


if (!API_BASE_URL) {
  throw new Error(
    "VITE_API_BASE_URL is not configured."
  );
}

if (!CSRF_COOKIE_NAME) {
  throw new Error(
    "VITE_CSRF_COOKIE_NAME is not configured."
  );
}

if (!CSRF_HEADER_NAME) {
  throw new Error(
    "VITE_CSRF_HEADER_NAME is not configured."
  );
}


const SELECTED_COMPANY_KEY = "selected_company";


// "*" is the development wildcard, not a real Tally company name.
export function getSelectedCompany() {
  const company = sessionStorage.getItem(
    SELECTED_COMPANY_KEY
  );

  return company && company !== "*"
    ? company
    : null;
}


export function setSelectedCompany(company) {
  if (company) {
    sessionStorage.setItem(
      SELECTED_COMPANY_KEY,
      company
    );
  } else {
    sessionStorage.removeItem(
      SELECTED_COMPANY_KEY
    );
  }
}


// Read a browser-readable cookie.
//
// Authentication cookies remain HttpOnly and cannot be read here.
// This helper is used only for the non-secret CSRF cookie.
function getCookie(name) {
  const encodedName =
    `${encodeURIComponent(name)}=`;

  const cookies = document.cookie
    ? document.cookie.split("; ")
    : [];

  for (const cookie of cookies) {
    if (cookie.startsWith(encodedName)) {
      return decodeURIComponent(
        cookie.substring(encodedName.length)
      );
    }
  }

  return null;
}


// Users assigned to several companies must name one on every report
// request, so the selected company is attached here once instead of
// in each page.
function withSelectedCompany(path) {
  const company = getSelectedCompany();

  if (
    !company ||
    /[?&]company_name=/.test(path)
  ) {
    return path;
  }

  const separator = path.includes("?")
    ? "&"
    : "?";

  return (
    `${path}${separator}` +
    `company_name=${encodeURIComponent(company)}`
  );
}


function buildHeaders(extraHeaders = {}) {
  return {
    "Content-Type": "application/json",
    ...extraHeaders,
  };
}


// Add the CSRF token to state-changing requests.
//
// The access token and refresh token are NOT read by JavaScript.
// They are sent automatically by the browser as HttpOnly cookies.
function buildCsrfHeaders(extraHeaders = {}) {
  const csrfToken = getCookie(
    CSRF_COOKIE_NAME
  );

  return buildHeaders({
    ...(csrfToken
      ? {
          [CSRF_HEADER_NAME]: csrfToken,
        }
      : {}),
    ...extraHeaders,
  });
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


// Only one refresh operation is allowed at a time.
//
// This is especially important because refresh tokens are rotated.
// If several failed API requests all refreshed independently,
// they could attempt to rotate the same refresh token.
let refreshPromise = null;


function isAuthPath(path) {
  return (
    path === "/auth/login" ||
    path === "/auth/refresh" ||
    path === "/auth/logout"
  );
}


async function refreshAuthentication() {
  if (!refreshPromise) {
    refreshPromise = fetch(
      `${API_BASE_URL}/auth/refresh`,
      {
        method: "POST",

        // Refresh is a state-changing authenticated request,
        // so it must include CSRF protection.
        headers: buildCsrfHeaders(),

        credentials: "include",
      }
    )
      .then(async (response) => {
        if (!response.ok) {
          let message =
            "Authentication session has expired.";

          try {
            const data = await response.json();

            message =
              data?.detail ||
              data?.message ||
              message;
          } catch {
            // Response may not contain JSON.
          }

          const error = new Error(message);
          error.status = response.status;

          throw error;
        }

        return true;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }

  return refreshPromise;
}


async function authenticatedFetch(
  path,
  options,
  retryOnUnauthorized = true
) {
  const response = await fetch(
    `${API_BASE_URL}${path}`,
    {
      ...options,
      credentials: "include",
    }
  );

  if (
    response.status !== 401 ||
    !retryOnUnauthorized ||
    isAuthPath(path)
  ) {
    return response;
  }

  // The access token may have expired.
  // Attempt one refresh and then retry the original request once.
  await refreshAuthentication();

  return fetch(
    `${API_BASE_URL}${path}`,
    {
      ...options,
      credentials: "include",
    }
  );
}


export async function apiGet(
  path,
  options = {}
) {
  const { signal } = options;

  const response = await authenticatedFetch(
    withSelectedCompany(path),
    {
      method: "GET",
      headers: buildHeaders(),
      signal,
    }
  );

  return handleResponse(response);
}


export async function apiPost(
  path,
  body
) {
  const response = await authenticatedFetch(
    path,
    {
      method: "POST",
      headers: buildCsrfHeaders(),
      body:
        body === undefined
          ? undefined
          : JSON.stringify(body),
    }
  );

  return handleResponse(response);
}


export async function apiPatch(
  path,
  body
) {
  const response = await authenticatedFetch(
    path,
    {
      method: "PATCH",
      headers: buildCsrfHeaders(),
      body:
        body === undefined
          ? undefined
          : JSON.stringify(body),
    }
  );

  return handleResponse(response);
}


export async function apiDelete(path) {
  const response = await authenticatedFetch(
    path,
    {
      method: "DELETE",
      headers: buildCsrfHeaders(),
    }
  );

  return handleResponse(response);
}


export async function downloadFile(
  path,
  filename = "download"
) {
  const response = await authenticatedFetch(
    withSelectedCompany(path),
    {
      method: "GET",
      headers: buildHeaders(),
    }
  );

  if (!response.ok) {
    let message =
      "Unable to download file.";

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

  const url =
    window.URL.createObjectURL(blob);

  const link =
    document.createElement("a");

  link.href = url;
  link.download = filename;

  document.body.appendChild(link);
  link.click();
  link.remove();

  window.URL.revokeObjectURL(url);
}
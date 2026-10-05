// Thin wrapper around the local HTTP API.
export class ApiError extends Error {}

export async function requestJson(path, { method = "GET", body, signal } = {}) {
  const response = await fetch(path, {
    method,
    signal,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const responseText = await response.text();
  const responseBody = responseText ? JSON.parse(responseText) : null;
  if (!response.ok) {
    const detail = responseBody && responseBody.detail;
    throw new ApiError(typeof detail === "string" ? detail : `Erreur HTTP ${response.status}`);
  }
  return responseBody;
}

export function buildQueryString(parameters) {
  const searchParameters = new URLSearchParams();
  for (const [parameterName, parameterValue] of Object.entries(parameters)) {
    if (parameterValue !== undefined && parameterValue !== null && parameterValue !== "") {
      searchParameters.set(parameterName, parameterValue);
    }
  }
  const queryString = searchParameters.toString();
  return queryString ? `?${queryString}` : "";
}

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

// Array values become repeated parameters, which the server reads as multiple choices
export function buildQueryString(parameters) {
  const searchParameters = new URLSearchParams();
  for (const [parameterName, parameterValue] of Object.entries(parameters)) {
    const values = Array.isArray(parameterValue) ? parameterValue : [parameterValue];
    values.filter((value) => value !== undefined && value !== null && value !== "").forEach((value) => searchParameters.append(parameterName, value));
  }
  const queryString = searchParameters.toString();
  return queryString ? `?${queryString}` : "";
}

export const API_BASE_URL = window.env?.API_BASE_URL;
export const ENDPOINT_URL = window.env?.ENDPOINT_URL;

export function getFullApiUrl() {
  return `${API_BASE_URL}${ENDPOINT_URL}`;
}

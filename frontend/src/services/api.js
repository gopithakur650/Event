import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:5000/api",
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  const csrf = document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith("csrf_access_token="))
    ?.slice("csrf_access_token=".length);
  if (csrf) config.headers["X-CSRF-TOKEN"] = decodeURIComponent(csrf);
  return config;
});

export function errorMessage(error) {
  if (typeof error.response?.data?.error === "string") {
    return error.response.data.error;
  }
  return error.message || "Something went wrong. Please try again.";
}

export async function downloadFile(path, filename) {
  const { data } = await api.get(path, { responseType: "blob" });
  const url = URL.createObjectURL(data);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export default api;

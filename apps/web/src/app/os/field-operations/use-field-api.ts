"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useMemo } from "react";

export function useFieldApi() {
  const { getToken } = useAuth();
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () =>
      process.env.NEXT_PUBLIC_DEV_USER_EMAIL ??
      "richardaustindugger@users.noreply.github.com",
    [],
  );

  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const token = await getToken().catch(() => null);
    return token
      ? { Authorization: `Bearer ${token}` }
      : { "X-Dev-User-Email": devUserEmail };
  }, [devUserEmail, getToken]);

  const request = useCallback(
    async <T,>(path: string, init?: RequestInit): Promise<T> => {
      const headers = new Headers(init?.headers);
      for (const [key, value] of Object.entries(await authHeaders())) {
        headers.set(key, value);
      }
      const response = await fetch(`${apiBaseUrl}${path}`, {
        ...init,
        headers,
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as {
          detail?: string | Array<{ msg?: string }>;
        } | null;
        const detail = Array.isArray(payload?.detail)
          ? payload.detail.map((item) => item.msg).filter(Boolean).join(" ")
          : payload?.detail;
        throw new Error(detail || "The operation could not be completed.");
      }
      if (response.status === 204) return {} as T;
      return (await response.json()) as T;
    },
    [apiBaseUrl, authHeaders],
  );

  const requestJson = useCallback(
    <T,>(path: string, method: string, body?: object) =>
      request<T>(path, {
        method,
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      }),
    [request],
  );

  const requestPhoto = useCallback(
    <T,>(path: string, image: Blob) =>
      request<T>(path, {
        method: "POST",
        headers: { "Content-Type": image.type || "image/jpeg" },
        body: image,
      }),
    [request],
  );

  const fetchBlob = useCallback(
    async (path: string) => {
      const headers = new Headers(await authHeaders());
      const response = await fetch(`${apiBaseUrl}${path}`, {
        headers,
      });
      if (!response.ok) throw new Error("The evidence image could not be loaded.");
      return response.blob();
    },
    [apiBaseUrl, authHeaders],
  );

  return { request, requestJson, requestPhoto, fetchBlob };
}

"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  EmailAdminPanel,
  type EmailSenderAlias,
} from "../../inbox/email-admin-panel";

type ConversationOption = {
  id: string;
  seller_name: string;
  property_address: string;
};

type EmailConfiguration = {
  items: EmailSenderAlias[];
  provider_configured: boolean;
  configuration_blockers: string[];
};

export function EmailSettingsWorkspace() {
  const { getToken } = useAuth();
  const [configuration, setConfiguration] = useState<EmailConfiguration>({
    items: [],
    provider_configured: false,
    configuration_blockers: [],
  });
  const [conversations, setConversations] = useState<ConversationOption[]>([]);
  const [error, setError] = useState("");
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

  const request = useCallback(
    async <T,>(path: string): Promise<T> => {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;
      const response = await fetch(`${apiBaseUrl}${path}`, {
        headers,
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`Request failed with status ${response.status}.`);
      return (await response.json()) as T;
    },
    [apiBaseUrl, devUserEmail, getToken],
  );

  const loadAliases = useCallback(async () => {
    const payload = await request<EmailConfiguration>("/api/v1/email/aliases");
    setConfiguration(payload);
  }, [request]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      void Promise.all([
        loadAliases(),
        request<{ items: ConversationOption[] }>("/api/v1/inbox/conversations")
          .then((payload) => setConversations(payload.items))
          .catch(() => setConversations([])),
      ]).catch((loadError: unknown) => {
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Email settings could not be loaded.",
        );
      });
    }, 0);
    return () => window.clearTimeout(handle);
  }, [loadAliases, request]);

  if (error) return <p role="alert">{error}</p>;

  return (
    <EmailAdminPanel
      aliases={configuration.items}
      configurationBlockers={configuration.configuration_blockers}
      conversations={conversations}
      onAliasesChanged={loadAliases}
      open
      providerConfigured={configuration.provider_configured}
      variant="inline"
    />
  );
}

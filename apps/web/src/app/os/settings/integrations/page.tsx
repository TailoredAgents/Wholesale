import { getIntegrationStatuses } from "../../../lib/api";
import { PageHeader, SectionPanel, WorkspacePage } from "../../_components/page-contracts";
import { requireSettingsSection } from "../section-access";
import styles from "../settings.module.css";

export const dynamic = "force-dynamic";

export default async function IntegrationSettingsPage() {
  await requireSettingsSection("integrations");
  const { integrations, apiConnected } = await getIntegrationStatuses();

  return (
    <WorkspacePage>
      <PageHeader
        description="See which external providers are ready without exposing credentials or secret values."
        eyebrow="Settings"
        meta={apiConnected ? `${integrations.filter((item) => item.configured).length} configured` : "API unavailable"}
        title="Integrations"
      />
      {apiConnected ? (
        <section className={styles.statusGrid} aria-label="Integration readiness">
          {integrations.map((integration) => (
            <article
              className={styles.statusCard}
              data-ready={integration.configured}
              key={integration.key}
            >
              <header>
                <div>
                  <span>{integration.category}</span>
                  <h3>{integration.name}</h3>
                </div>
                <strong>{integration.configured ? "Ready" : integration.enabled ? "Needs setup" : "Off"}</strong>
              </header>
              <small>Mode: {integration.mode}</small>
              {integration.runtime_status ? (
                <small>Runtime: {integration.runtime_status.replaceAll("_", " ")}</small>
              ) : null}
              {integration.last_success_at ? (
                <small>Last successful sync: {new Date(integration.last_success_at).toLocaleString()}</small>
              ) : null}
              {(integration.details ?? []).map((detail) => (
                <small key={detail}>{detail}</small>
              ))}
              {integration.blockers.length ? (
                <div className={styles.blockers}>
                  {integration.blockers.map((blocker) => (
                    <span key={blocker}>{blocker}</span>
                  ))}
                </div>
              ) : (
                <small>No missing configuration detected.</small>
              )}
            </article>
          ))}
        </section>
      ) : (
        <SectionPanel description="Check API authentication and deployment status." title="Integration status unavailable">
          <div />
        </SectionPanel>
      )}
    </WorkspacePage>
  );
}

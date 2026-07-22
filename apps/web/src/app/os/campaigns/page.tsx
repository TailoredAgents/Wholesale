import { getCampaignManagementOverview } from "../../lib/api";
import styles from "../page.module.css";
import { CampaignManagementWorkspace } from "./campaign-management-workspace";

export const dynamic = "force-dynamic";

export default async function CampaignsPage() {
  const { campaignManagement, apiConnected } = await getCampaignManagementOverview();

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Campaign and list management</p>
          <h2>Outreach control center</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Prospect data</span>
          <strong className={apiConnected ? styles.ready : styles.warning}>
            {apiConnected ? "Screened and traceable" : "API unavailable"}
          </strong>
        </div>
      </header>

      {campaignManagement ? (
        <CampaignManagementWorkspace data={campaignManagement} />
      ) : (
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Campaign management unavailable</h3>
            <span>Acquisition-management access is required</span>
          </div>
        </section>
      )}
    </>
  );
}

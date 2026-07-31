import AiControlPage from "../../ai/ai-control-page";
import { requireSettingsSection } from "../section-access";

export const dynamic = "force-dynamic";

export default async function AiSettingsPage() {
  await requireSettingsSection("ai");
  return <AiControlPage />;
}

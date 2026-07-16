import { SellerSituationPage } from "../seller-situation-page";
import { getSellerSituation } from "../seller-situations";

export const metadata = {
  title: "Sell a House That Needs Repairs | Stonegate Home Buyers",
  description: "Request a cash offer for a Georgia property that needs repairs.",
};

export default function SellHouseNeedsRepairsPage() {
  const situation = getSellerSituation("sell-house-needs-repairs");
  if (!situation) {
    return null;
  }
  return <SellerSituationPage situation={situation} />;
}

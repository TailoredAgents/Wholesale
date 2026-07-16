import { SellerSituationPage } from "../seller-situation-page";
import { getSellerSituation } from "../seller-situations";

export const metadata = {
  title: "Sell an Inherited House | Stonegate Home Buyers",
  description: "Request a cash offer for an inherited Georgia property.",
};

export default function SellInheritedHousePage() {
  const situation = getSellerSituation("sell-inherited-house");
  if (!situation) {
    return null;
  }
  return <SellerSituationPage situation={situation} />;
}

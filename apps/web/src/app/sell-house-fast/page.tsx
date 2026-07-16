import { SellerSituationPage } from "../seller-situation-page";
import { getSellerSituation } from "../seller-situations";

export const metadata = {
  title: "Sell Your House Fast | Stonegate Home Buyers",
  description: "Request a cash offer when you need a faster Georgia home sale option.",
};

export default function SellHouseFastPage() {
  const situation = getSellerSituation("sell-house-fast");
  if (!situation) {
    return null;
  }
  return <SellerSituationPage situation={situation} />;
}

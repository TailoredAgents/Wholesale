import { notFound } from "next/navigation";

import { DesignSystemReference } from "./reference";

export const metadata = {
  title: "Stonegate UI Reference",
};

export default function DesignSystemPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <DesignSystemReference />;
}

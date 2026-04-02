import { IndustryReturns } from "@/components/IndustryReturns";

export const revalidate = 300;
export const dynamic = "force-dynamic";

async function getData() {
  const res = await fetch(`/api/industry-returns`, {
    next: { revalidate: 3600 }
  });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function IndustryReturnsPage() {
  const data = await getData();
  return <IndustryReturns data={data} />;
}

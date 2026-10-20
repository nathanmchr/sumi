import { HomophoneBrowser } from "@/components/homophone-browser";

export default async function HomophonesPage({ searchParams }: {
  searchParams: Promise<{ q?: string | string[] }>;
}) {
  const params = await searchParams;
  const query = (typeof params.q === "string" ? params.q : "").slice(0, 100);
  return <HomophoneBrowser key={query} initialQuery={query} />;
}

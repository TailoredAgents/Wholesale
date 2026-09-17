export const dynamic = "force-dynamic";

export function GET() {
  return Response.json(
    { status: "ok", service: "web" },
    { headers: { "Cache-Control": "no-store" } },
  );
}

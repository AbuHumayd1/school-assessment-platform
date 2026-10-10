const RAILWAY_ORIGIN =
  "https://school-assessment-platform-production.up.railway.app";

export async function onRequest(context) {
  const incomingUrl = new URL(context.request.url);

  const targetUrl = new URL(
    incomingUrl.pathname + incomingUrl.search,
    RAILWAY_ORIGIN
  );

  const headers = new Headers(context.request.headers);

  // Let fetch generate the correct Host header for Railway.
  headers.delete("host");

  const requestInit = {
    method: context.request.method,
    headers,
    redirect: "manual",
  };

  if (!["GET", "HEAD"].includes(context.request.method)) {
    requestInit.body = context.request.body;
  }

  return fetch(targetUrl.toString(), requestInit);
}
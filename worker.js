/* ============================================================================
   THE ARTS WIRE — payment → email "glue"  (Cloudflare Worker)
   ============================================================================
   When someone subscribes (or cancels) through Lemon Squeezy, Lemon Squeezy
   sends a webhook here. This Worker verifies it's genuine, then adds the
   reader to your MailerLite list with their chosen language saved as a field
   (so your sender knows which translated edition to deliver). On cancel, it
   marks them unsubscribed.

   Secrets to set (see glue/README.md):
     LS_WEBHOOK_SECRET     - the signing secret from your Lemon Squeezy webhook
     MAILERLITE_API_KEY    - your MailerLite API token
   Optional var:
     MAILERLITE_GROUP_ID   - a group to add subscribers to (else just the list)

   Using Paddle instead? The shape differs (signature header + event names +
   custom data path). Notes are at the bottom of this file.
============================================================================ */

const ML_API = "https://connect.mailerlite.com/api";

// Verify Lemon Squeezy's HMAC-SHA256 signature over the raw request body.
export async function verifySignature(secret, rawBody, signatureHex) {
  if (!secret || !signatureHex) return false;
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(rawBody));
  const expected = [...new Uint8Array(mac)]
    .map((b) => b.toString(16).padStart(2, "0")).join("");
  // constant-time-ish comparison
  if (expected.length !== signatureHex.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) diff |= expected.charCodeAt(i) ^ signatureHex.charCodeAt(i);
  return diff === 0;
}

function pickEmail(attrs = {}) {
  return attrs.user_email || attrs.customer_email || attrs.email || null;
}

// Upsert a subscriber in MailerLite with their language; optionally add a group.
async function upsertSubscriber(env, email, lang, name, status) {
  const body = {
    email,
    fields: { language: lang, name: name || "" },
    status: status || "active",
  };
  if (env.MAILERLITE_GROUP_ID) body.groups = [env.MAILERLITE_GROUP_ID];
  const res = await fetch(`${ML_API}/subscribers`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json",
      "Authorization": `Bearer ${env.MAILERLITE_API_KEY}`,
    },
    body: JSON.stringify(body),
  });
  return res.ok;
}

export async function handle(request, env) {
  if (request.method !== "POST") return new Response("OK", { status: 200 });

  const raw = await request.text();
  const sig = request.headers.get("X-Signature") || "";
  const ok = await verifySignature(env.LS_WEBHOOK_SECRET, raw, sig);
  if (!ok) return new Response("bad signature", { status: 401 });

  let payload;
  try { payload = JSON.parse(raw); }
  catch { return new Response("bad json", { status: 400 }); }

  const event = payload?.meta?.event_name || "";
  const lang = payload?.meta?.custom_data?.lang || "en";
  const attrs = payload?.data?.attributes || {};
  const email = pickEmail(attrs);
  const name = attrs.user_name || "";

  if (!email) return new Response("no email", { status: 202 });

  const ADD = ["subscription_created", "subscription_updated",
               "subscription_resumed", "order_created"];
  const REMOVE = ["subscription_cancelled", "subscription_expired"];

  let done = true;
  if (ADD.includes(event)) {
    done = await upsertSubscriber(env, email, lang, name, "active");
  } else if (REMOVE.includes(event)) {
    done = await upsertSubscriber(env, email, lang, name, "unsubscribed");
  } // other events: acknowledge and ignore

  return new Response(done ? "ok" : "downstream error", { status: done ? 200 : 502 });
}

export default { fetch: (request, env) => handle(request, env) };

/* ----------------------------------------------------------------------------
   PADDLE NOTES (if you choose Paddle instead of Lemon Squeezy):
   - Signature header is "Paddle-Signature" (ts + h1 HMAC); verify per Paddle docs.
   - Event types look like "subscription.activated" / "subscription.canceled".
   - The email is at data.customer? / data.custom_data carries your lang field.
   Swap pickEmail(), the event-name lists, and verifySignature accordingly.
---------------------------------------------------------------------------- */

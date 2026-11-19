// Envía los correos del agente. Solo acepta peticiones firmadas por GitHub Actions de este repositorio
// (token OIDC), así no hace falta guardar contraseñas en GitHub.
// Variables en Vercel: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_TO, NOTIFY_REPO (usuario/repo)
const crypto = require("crypto");
const nodemailer = require("nodemailer");

const ISSUER = "https://token.actions.githubusercontent.com";
const AUDIENCE = "empleo-gc";
let jwksCache = { at: 0, keys: [] };

const b64 = s => Buffer.from(s.replace(/-/g, "+").replace(/_/g, "/"), "base64");

async function jwks() {
  if (Date.now() - jwksCache.at < 3600e3 && jwksCache.keys.length) return jwksCache.keys;
  const r = await fetch(`${ISSUER}/.well-known/jwks`);
  if (!r.ok) throw new Error("no se pudo obtener JWKS de GitHub");
  jwksCache = { at: Date.now(), keys: (await r.json()).keys };
  return jwksCache.keys;
}

async function verify(token) {
  const [h, p, s] = String(token || "").split(".");
  if (!s) throw new Error("token mal formado");
  const header = JSON.parse(b64(h).toString());
  if (header.alg !== "RS256") throw new Error("algoritmo no admitido");
  const jwk = (await jwks()).find(k => k.kid === header.kid);
  if (!jwk) throw new Error("clave desconocida");
  const key = crypto.createPublicKey({ key: jwk, format: "jwk" });
  if (!crypto.verify("RSA-SHA256", Buffer.from(`${h}.${p}`), key, b64(s))) throw new Error("firma no válida");
  const c = JSON.parse(b64(p).toString());
  const now = Math.floor(Date.now() / 1000);
  if (c.iss !== ISSUER) throw new Error("emisor no válido");
  if (c.aud !== AUDIENCE) throw new Error("audiencia no válida");
  if (!(c.exp > now) || (c.nbf && c.nbf > now + 60)) throw new Error("token caducado");
  if (String(c.repository).toLowerCase() !== String(process.env.NOTIFY_REPO).toLowerCase())
    throw new Error("repositorio no autorizado");
  return c;
}

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ error: "método no permitido" });
  const { SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_TO, NOTIFY_REPO } = process.env;
  if (!SMTP_HOST || !SMTP_USER || !SMTP_PASSWORD || !EMAIL_TO || !NOTIFY_REPO)
    return res.status(503).json({ error: "correo sin configurar" });
  try {
    await verify((req.headers.authorization || "").replace(/^Bearer\s+/i, ""));
  } catch (e) {
    return res.status(401).json({ error: String(e.message || e) });
  }
  const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : (req.body || {});
  const subject = String(body.subject || "Informe de empleo").slice(0, 200);
  try {
    const port = Number(SMTP_PORT || 587);
    const t = nodemailer.createTransport({ host: SMTP_HOST, port, secure: port === 465,
      auth: { user: SMTP_USER, pass: SMTP_PASSWORD } });
    await t.sendMail({ from: `"Agente de empleo GC" <${SMTP_USER}>`, to: EMAIL_TO, subject,
      text: String(body.text || ""), ...(body.html ? { html: String(body.html) } : {}) });
    return res.status(200).json({ ok: true });
  } catch (e) {
    return res.status(502).json({ error: "fallo SMTP: " + String(e.message || e).slice(0, 200) });
  }
};

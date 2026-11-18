// Función de Vercel: acciones del panel protegidas por PIN.
//  - flag: marca/desmarca favorita o descartada (guarda site/flags.json en el repositorio)
//  - run:  lanza una búsqueda manual en GitHub Actions
// Variables de entorno en Vercel: PANEL_PIN, GITHUB_TOKEN (token de acceso fino al repo), GITHUB_REPO (usuario/repo)
const crypto = require("crypto");

const GH = "https://api.github.com";
const FLAGS_PATH = "site/flags.json";
const attempts = new Map(); // freno básico contra adivinar el PIN (por instancia)

function sameSecret(a, b) {
  const x = Buffer.from(String(a || "")), y = Buffer.from(String(b || ""));
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}

async function gh(path, opts = {}) {
  const r = await fetch(GH + path, {
    ...opts,
    headers: {
      Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "job-agent-panel",
      ...(opts.headers || {}),
    },
  });
  return r;
}

async function updateFlags(id, flag, value, retries = 2) {
  const repo = process.env.GITHUB_REPO;
  const cur = await gh(`/repos/${repo}/contents/${FLAGS_PATH}?ref=main`);
  let data = { favorite: [], discarded: [] }, sha;
  if (cur.ok) {
    const j = await cur.json();
    sha = j.sha;
    try { data = JSON.parse(Buffer.from(j.content, "base64").toString("utf8")); } catch {}
  } else if (cur.status !== 404) {
    throw new Error(`GitHub ${cur.status}`);
  }
  const set = new Set((data[flag] || []).map(Number));
  value ? set.add(id) : set.delete(id);
  data[flag] = [...set].sort((a, b) => a - b);
  if (flag === "favorite" && value) data.discarded = (data.discarded || []).filter(x => x !== id);
  if (flag === "discarded" && value) data.favorite = (data.favorite || []).filter(x => x !== id);
  const put = await gh(`/repos/${repo}/contents/${FLAGS_PATH}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: `Panel: ${flag === "favorite" ? "favorita" : "descartada"} ${value ? "+" : "-"} #${id}`,
      content: Buffer.from(JSON.stringify(data, null, 1) + "\n").toString("base64"),
      branch: "main",
      ...(sha ? { sha } : {}),
    }),
  });
  if (put.status === 409 && retries > 0) return updateFlags(id, flag, value, retries - 1); // cambio simultáneo
  if (!put.ok) throw new Error(`GitHub ${put.status}`);
}

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ error: "método no permitido" });
  const { PANEL_PIN, GITHUB_TOKEN, GITHUB_REPO } = process.env;
  if (!PANEL_PIN || !GITHUB_TOKEN || !GITHUB_REPO) return res.status(503).json({ error: "panel sin configurar" });

  const ip = (req.headers["x-forwarded-for"] || "").split(",")[0].trim() || "?";
  const a = attempts.get(ip) || { n: 0, t: Date.now() };
  if (Date.now() - a.t > 15 * 60 * 1000) { a.n = 0; a.t = Date.now(); }
  if (a.n >= 10) return res.status(429).json({ error: "demasiados intentos, espera 15 minutos" });

  const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : (req.body || {});
  if (!sameSecret(body.pin, PANEL_PIN)) {
    a.n += 1; attempts.set(ip, a);
    return res.status(401).json({ error: "PIN incorrecto" });
  }
  try {
    if (body.accion === "flag") {
      const id = Number(body.id);
      if (!Number.isInteger(id) || id <= 0 || !["favorite", "discarded"].includes(body.flag))
        return res.status(400).json({ error: "datos no válidos" });
      await updateFlags(id, body.flag, !!body.value);
      return res.status(200).json({ ok: true });
    }
    if (body.accion === "run") {
      const r = await gh(`/repos/${GITHUB_REPO}/actions/workflows/daily.yml/dispatches`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ref: "main", inputs: { modo: "manual" } }),
      });
      if (!r.ok) throw new Error(`GitHub ${r.status}`);
      return res.status(200).json({ ok: true });
    }
    return res.status(400).json({ error: "acción desconocida" });
  } catch (e) {
    return res.status(502).json({ error: String(e.message || e) });
  }
};

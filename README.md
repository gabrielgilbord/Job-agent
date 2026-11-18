# Agente de empleo — Gran Canaria

Busca ofertas cada mañana a las **08:30 (hora canaria)**, las puntúa de 0 a 100 según el perfil de la candidata
(Grado en Turismo + Comercio Internacional + experiencia en tienda), guarda el historial y envía un **informe diario**
por Telegram y/o correo. Funciona solo, en GitHub Actions, sin abrir Claude ni tener el ordenador encendido.

> El agente **nunca** se inscribe en ofertas ni escribe a empresas. Solo busca, filtra y avisa.

## Cómo funciona

```
GitHub Actions (cron) ─► main.py run --scheduled
   ├─ search/        Turijobs · SmartRecruiters (Primark, Kiabi…) · Adzuna* · InfoJobs* · Jooble*   (*con API key gratuita)
   ├─ filters/geo    municipio, tiempo en coche desde San Mateo, descarte de otras islas/península
   ├─ scoring/       categoría A–E + puntuación razonada (estudios 25, experiencia 20, ubicación 20,
   │                 condiciones 20, crecimiento 10, intereses 5) − penalizaciones
   ├─ database.py    SQLite (data/jobs.db): nueva · comunicada · modificada · cerrada · republicada
   ├─ reports/       informe HTML (reports_out/) + resumen para Telegram
   └─ notifications/ Telegram y/o correo; alerta inmediata si una oferta supera 90
```

- **Hora canaria real**: GitHub solo entiende UTC, así que el flujo se lanza a las 07:30 y 08:30 UTC y el programa
  solo ejecuta el que coincide con las 08:30 en Canarias (vale para invierno y verano; nunca duplica el informe).
  GitHub puede retrasar los cron unos minutos (a veces 10–20) en horas de mucha carga.
- **Revisión de tarde (14:30 UTC)**: búsqueda rápida que solo avisa si aparece una oferta > 90.
- **Sin duplicados**: se identifica cada oferta por URL y por empresa+puesto+municipio (detecta la misma oferta en
  dos portales). Una oferta ya comunicada no vuelve a salir salvo que cambie (salario, contrato, jornada) o se republique.
- **Caducadas**: si una oferta deja de aparecer 3 ejecuciones seguidas (solo cuenta si su portal respondió bien) o
  pasa su fecha de caducidad, se marca como cerrada.
- **Errores**: si un portal falla, se registra (logs/agent.log y pie del informe) y el resto sigue. Las peticiones
  fallidas se reintentan con espera progresiva.
- **Coste**: 0 €. Repositorio privado: el plan gratuito de GitHub incluye 2.000 min/mes; esto usa ~150.

## Puesta en marcha (una sola vez)

### 1. Telegram (recomendado, 3 minutos)
1. En Telegram abre **@BotFather** → `/newbot` → ponle nombre → copia el **token**.
2. Abre tu bot nuevo y mándale cualquier mensaje (p. ej. «hola»).
3. Visita `https://api.telegram.org/bot<TOKEN>/getUpdates` y copia el número `"chat":{"id": …}`.
   Si queréis recibirlo dos personas, cada una escribe al bot y se ponen los ids separados por comas.

### 2. Secretos en GitHub
Repositorio → **Settings → Secrets and variables → Actions → New repository secret**:

| Secreto | Obligatorio | Valor |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | para Telegram | token de BotFather |
| `TELEGRAM_CHAT_ID` | para Telegram | id(s) del chat |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO` | para correo | p. ej. `smtp.gmail.com`, `587`, tu Gmail, [contraseña de aplicación](https://myaccount.google.com/apppasswords), destinatario |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | opcional | alta gratis en developer.adzuna.com |
| `INFOJOBS_CLIENT_ID`, `INFOJOBS_CLIENT_SECRET` | opcional | alta gratis en developer.infojobs.net |
| `JOOBLE_API_KEY` | opcional | alta gratis en jooble.org/api/about |

Las fuentes opcionales amplían mucho la cobertura (InfoJobs es el portal más grande; Adzuna y Jooble agregan
Indeed y portales de empresa). Sin ellas el agente funciona igual con Turijobs y SmartRecruiters.

### 3. Probar
**Actions → Búsqueda diaria de empleo → Run workflow → modo `run`**. En 1–2 minutos llega el informe.
A partir de ahí se ejecuta solo cada día.

## Cambiar preferencias
Todo está en **`config.yaml`** (se edita desde la web de GitHub, botón del lápiz): hora, tiempo máximo de
desplazamiento, puntuación mínima, jornada/contrato/salario deseados, categorías y términos de búsqueda,
municipios por prioridad, empresas a vigilar, idiomas o carnet **cuando estén confirmados**
(`idiomas_confirmados`, `carnet_conducir`). Lo que no esté confirmado se marca en el informe como «a confirmar».

Para cambiar la hora: edita `hora_local` **y** las dos líneas `cron` de `.github/workflows/daily.yml`
(la hora deseada menos 1 en verano y tal cual en invierno, en UTC).

## Detenerlo
- Pausa: **Actions → Búsqueda diaria de empleo → ··· → Disable workflow** (se reactiva igual).
- Para siempre: borra el repositorio.
- Borrar historial: `python main.py reset-history` (en local) o borra `data/jobs.db` desde GitHub.

## Uso en local (opcional)
```bash
pip install -r requirements.txt
cp .env.example .env          # rellena lo que quieras usar
python main.py run --no-notify   # búsqueda + informe en reports_out/ultimo_informe.html
python main.py test-notify       # comprueba Telegram/correo
python main.py dashboard         # panel: http://127.0.0.1:8765
pytest -q                        # pruebas (RUN_LIVE=1 para probar los portales reales)
```
El **panel** permite ver y filtrar ofertas por localidad, categoría, estado y puntuación, marcar favoritas o
descartadas, ver el último informe y lanzar una búsqueda manual. Para usarlo con los datos de GitHub, haz
`git pull` antes (la base de datos se actualiza en el repositorio cada día).

## Fuentes y normas de uso
- **Turijobs**: listado público de Gran Canaria (permitido por su robots.txt), 1 consulta cada 2 s.
- **SmartRecruiters**: API pública de publicaciones de empresas (Primark y Kiabi tienen tiendas en GC; se pueden
  añadir más identificadores en `config.yaml`).
- **InfoJobs / Adzuna / Jooble**: APIs oficiales con clave gratuita.
- **No incluidas**: LinkedIn e Indeed no permiten el acceso automatizado en sus condiciones (Indeed llega en parte a
  través de Adzuna/Jooble). El Servicio Canario de Empleo y Empléate no ofrecen un listado o API pública consultable;
  las ofertas del SCE se publican también en portales agregados. Las webs de hoteles y comercios locales aparecen en
  «Empresas que merece la pena seguir» con su enlace.
- No se usan CAPTCHAs, inicios de sesión ni datos privados.

## Tiempos de desplazamiento
Estimaciones de conducción por carretera desde Vega de San Mateo (OSRM, red viaria real, sin tráfico):
Santa Brígida 14 min · Valsequillo 20 · Teror 24 · Telde 33 · Las Palmas 35 · Arucas 38 · Ingenio 45 ·
Agüimes 51 · Gáldar 54 · Maspalomas 58 · Mogán 82. En hora punta hacia Las Palmas/Telde suma ~10 min.

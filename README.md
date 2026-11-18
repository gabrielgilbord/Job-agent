# Agente de empleo — Gran Canaria

Busca ofertas cada mañana a las **08:30 (hora canaria)**, las puntúa de 0 a 100 según el perfil de la candidata
(Grado en Turismo + Comercio Internacional + experiencia en tienda), guarda el historial, envía un **informe diario por correo** y publica un **panel web** con todas las ofertas.
Funciona solo, en GitHub Actions + Vercel, sin abrir Claude ni tener el ordenador encendido.

> El agente **nunca** se inscribe en ofertas ni escribe a empresas. Solo busca, filtra y avisa.

## Cómo funciona

```
GitHub Actions (cron) ─► main.py run --scheduled
   ├─ search/        Turijobs · SmartRecruiters (Primark, Kiabi…) · Adzuna* · InfoJobs* · Jooble*   (*con API key gratuita)
   ├─ filters/geo    municipio, tiempo en coche desde San Mateo, descarte de otras islas/península
   ├─ scoring/       categoría A–E + puntuación razonada (estudios 25, experiencia 20, ubicación 20,
   │                 condiciones 20, crecimiento 10, intereses 5) − penalizaciones
   ├─ database.py    SQLite (data/jobs.db): nueva · comunicada · modificada · cerrada · republicada
   ├─ reports/       informe HTML (reports_out/), que es el cuerpo del correo
   ├─ notifications/ correo; aviso inmediato si una oferta supera 90
   └─ webpanel.py    publica site/data.json  ─►  Vercel redespliega el panel (site/) en cada actualización
```

- **Hora canaria real**: GitHub solo entiende UTC, así que el flujo se lanza a las 07:30 y 08:30 UTC y el programa
  solo ejecuta el que coincide con las 08:30 en Canarias (vale para invierno y verano; nunca duplica el informe).
  GitHub puede retrasar los cron unos minutos (a veces 10–20) en horas de mucha carga.
- **Revisión de tarde (14:30 UTC)**: búsqueda que actualiza el panel y solo manda correo si aparece una oferta > 90.
- **Sin duplicados**: se identifica cada oferta por URL y por empresa+puesto+municipio (detecta la misma oferta en
  dos portales). Una oferta ya comunicada no vuelve a salir salvo que cambie (salario, contrato, jornada) o se republique.
- **Caducadas**: si una oferta deja de aparecer 3 ejecuciones seguidas (solo cuenta si su portal respondió bien) o
  pasa su fecha de caducidad, se marca como cerrada.
- **Errores**: si un portal falla, se registra (logs/agent.log y pie del informe) y el resto sigue. Las peticiones
  fallidas se reintentan con espera progresiva.
- **Coste**: 0 €. Repositorio privado: el plan gratuito de GitHub incluye 2.000 min/mes; esto usa ~150.

## Puesta en marcha (una sola vez)

### 1. Correo (Gmail)
1. Activa la verificación en dos pasos de la cuenta de Gmail que enviará los correos.
2. Crea una contraseña de aplicación en https://myaccount.google.com/apppasswords (16 letras).

### 2. Secretos en GitHub
Repositorio → **Settings → Secrets and variables → Actions → New repository secret**:

| Secreto | Valor |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | el Gmail que envía |
| `SMTP_PASSWORD` | la contraseña de aplicación |
| `EMAIL_TO` | quién recibe el informe (varios separados por comas) |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | opcional · alta gratis en developer.adzuna.com |
| `INFOJOBS_CLIENT_ID`, `INFOJOBS_CLIENT_SECRET` | opcional · alta gratis en developer.infojobs.net |
| `JOOBLE_API_KEY` | opcional · alta gratis en jooble.org/api/about |

Las fuentes opcionales amplían mucho la cobertura (InfoJobs es el portal más grande; Adzuna y Jooble agregan
Indeed y portales de empresa). Sin ellas el agente funciona igual con Turijobs y SmartRecruiters.

### 3. Panel web (Vercel)
El panel es la carpeta `site/`: una página estática que lee `data.json` (se regenera en cada búsqueda) y una
función `api/accion.js` para marcar favoritas/descartadas y lanzar búsquedas. **Cualquiera con el enlace puede
ver las ofertas** (la página no se indexa en buscadores y no muestra datos personales de la candidata), pero
**solo quien conoce el PIN puede modificar**.

- Proyecto de Vercel conectado a este repositorio con **Root Directory = `site`**.
- Variables de entorno del proyecto en Vercel:
  - `PANEL_PIN`: el PIN para marcar ofertas o lanzar búsquedas.
  - `GITHUB_REPO`: `gabrielgilbord/job-agent`.
  - `GITHUB_TOKEN`: token de GitHub *fine-grained* (github.com/settings/personal-access-tokens/new) con acceso
    **solo a este repositorio** y permisos **Contents: Read and write** y **Actions: Read and write**.
- Pon la dirección del panel en `panel_url` de `config.yaml` para que salga enlazada en los correos.

Las favoritas/descartadas se guardan en `site/flags.json` del repositorio; el panel tarda ~1 minuto en reflejarlas
para otros dispositivos (en el tuyo se ven al instante).

### 4. Probar
**Actions → Búsqueda diaria de empleo → Run workflow → modo `run`**. En 1–2 minutos llega el correo y se
actualiza el panel. A partir de ahí se ejecuta solo cada día.

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
python main.py test-notify       # comprueba el correo
pytest -q                        # pruebas (RUN_LIVE=1 para probar los portales reales)
cd site && python -m http.server # ver el panel en local (solo lectura)
```
El **panel** permite ver y filtrar ofertas por texto, localidad, categoría, estado y puntuación, ordenar por
cercanía o fecha, marcar favoritas o descartadas, ver el historial de búsquedas y lanzar una búsqueda manual.

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

# Altylab Honeycomb Studio

Generate Bambu Studio-ready watertight honeycomb STL panels and optional SVG patterns.

This is an open-source web version of the Honeycomb 3D Design plugin.

## Local development

```bash
docker compose up --build -d
curl http://127.0.0.1:8765/api/health
```

Open http://127.0.0.1:8765 locally. The Compose file binds the service to localhost intentionally.

## Deployment

Use `deploy/nginx.conf` as a starting point for your existing Nginx server. Point the Cloudflare Tunnel hostname `honeycomb.altylab.com` at the Nginx HTTPS/HTTP service you already operate. Do not expose the Python API directly to the internet.

## Features

- Exact literal Bambu X/Y/Z millimeter inputs
- Auto-select unique smallest axis as panel thickness, or override
- Bin, clean, large honeycomb presets
- Adjustable hole point-to-point size, rib, border
- Centered full through-holes
- STL export with dimensional and watertightness checks
- SVG preview and optional SVG export
- Optional custom download filename for STL and SVG (extension added automatically)
- Flat-on-bed output orientation option

SVG represents a 2D face only; 3D thickness must be set in Bambu Studio.

## Important

Public generation is CPU-intensive. The app bounds dimensions, concurrent jobs and resources, but **add request-rate limiting at the reverse proxy** before widely advertising the service.

## Tests

```bash
pip install -r requirements.txt pytest httpx
pytest -q
```

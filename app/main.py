"""Honeycomb Altylab API. No persistent user files, no account required."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from .geometry import layout_info, svg_string, mesh_for_panel

ROOT = Path(__file__).parent
app = FastAPI(title='Altylab Honeycomb Generator', docs_url=None, redoc_url=None)
POOL = ThreadPoolExecutor(max_workers=2)
CAPACITY = asyncio.Semaphore(2)

class Design(BaseModel):
    model_config = ConfigDict(extra='forbid')
    x: float = Field(default=170, gt=0, le=256)
    y: float = Field(default=120, gt=0, le=256)
    z: float = Field(default=3, gt=0, le=256)
    thickness_axis: str = Field(default='auto', pattern='^(auto|x|y|z)$')
    style: str = Field(default='bin', pattern='^(bin|clean|large)$')
    hole_size: float | None = Field(default=None, gt=0, le=100)
    rib: float | None = Field(default=None, gt=0, le=50)
    border: float | None = Field(default=None, ge=0, le=60)
    flat: bool = False

def info_for(d):
    return layout_info(d.x,d.y,d.z,d.thickness_axis,d.style,d.hole_size,d.rib,d.border)

@app.get('/api/health')
def health():
    return {'ok': True}

@app.post('/api/preview')
def preview(d: Design):
    try:
        i = info_for(d)
        return {'svg': svg_string(i), 'holes': i['holes'], 'axis': i['axis'],
                'hole_size': i['hole_size'], 'fallback': i['fallback'],
                'face': [i['width'],i['height']],
                'output': list({'x': (d.y,d.z,d.x), 'y': (d.x,d.z,d.y), 'z': (d.x,d.y,d.z)}[i['axis']] if d.flat else (d.x,d.y,d.z))}
    except ValueError as exc:
        raise HTTPException(422,str(exc))

@app.post('/api/download/{kind}')
async def download(kind: str, d: Design):
    if kind not in ('stl','svg'):
        raise HTTPException(404,'Unknown output format')
    try:
        i = info_for(d)
    except ValueError as exc:
        raise HTTPException(422,str(exc))
    dims = {'x':(d.y,d.z,d.x),'y':(d.x,d.z,d.y),'z':(d.x,d.y,d.z)}[i['axis']] if d.flat else (d.x,d.y,d.z)
    fname = ('honeycomb_'+'_'.join(f'{a}{v:g}' for a,v in zip('XYZ',dims))+('_flat' if d.flat else '')+'.'+kind)
    headers = {'Content-Disposition':f'attachment; filename="{fname}"', 'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
    if kind == 'svg':
        return Response(svg_string(i),media_type='image/svg+xml',headers=headers)
    async with CAPACITY:
        try:
            loop = asyncio.get_running_loop()
            mesh = await asyncio.wait_for(loop.run_in_executor(POOL,mesh_for_panel,d.x,d.y,d.z,i,d.flat),timeout=25)
            data = mesh.export(file_type='stl')
            return Response(data, media_type='model/stl',headers=headers)
        except (ValueError,RuntimeError) as exc:
            raise HTTPException(422,str(exc))
        except asyncio.TimeoutError:
            raise HTTPException(503,'Generation is taking too long. Try a smaller panel or larger holes.')

@app.get('/')
def index():
    return FileResponse(ROOT/'static/index.html')
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')

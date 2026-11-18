import io
import re
import xml.etree.ElementTree as ET
import numpy as np
import trimesh
from fastapi.testclient import TestClient
from app.main import app

client=TestClient(app)

def test_examples():
    for dims in [(170,120,3),(3,120,42),(164,3,42)]:
        req=dict(zip('xyz',dims))
        p=client.post('/api/preview',json=req)
        assert p.status_code==200,p.text
        assert p.json()['holes']>0
        svg=client.post('/api/download/svg',json=req)
        assert svg.status_code==200
        ET.fromstring(svg.text)
        s=client.post('/api/download/stl',json=req)
        assert s.status_code==200,s.text
        mesh=trimesh.load(io.BytesIO(s.content),file_type='stl')
        assert mesh.is_watertight and mesh.is_winding_consistent
        assert np.allclose(mesh.extents,dims,atol=.01)

def test_flat_and_validation():
    r=client.post('/api/download/stl',json={'x':3,'y':120,'z':42,'flat':True})
    assert r.status_code==200,r.text
    mesh=trimesh.load(io.BytesIO(r.content),file_type='stl')
    assert np.allclose(mesh.extents,[120,42,3],atol=.01)
    assert client.post('/api/preview',json={'x':3,'y':3,'z':42}).status_code==422
    assert client.post('/api/preview',json={'x':270,'y':120,'z':3}).status_code==422
    assert client.post('/api/preview',json={'x':3,'y':10,'z':10,'hole_size':50}).status_code==422


def test_custom_download_filename_and_format():
    req={'x':30,'y':30,'z':3,'filename':'My panel.SVG'}
    for kind in ('svg','stl'):
        r=client.post(f'/api/download/{kind}',json=req)
        assert r.status_code==200,r.text
        assert r.headers['content-disposition']==f'attachment; filename="My panel.{kind}"'


def test_filename_fallback_and_sanitization():
    cases={
        None:'honeycomb_X30_Y30_Z3.svg',
        '   ':'honeycomb_X30_Y30_Z3.svg',
        '../../new/panel':'panel.svg',
        r'C:\temp\panel.stl':'panel.svg',
        'bad"; filename="wrong\r\nX-Evil: yes':'bad_filename_wrong_X-Evil_yes.svg',
        '..':'honeycomb_X30_Y30_Z3.svg',
        'CON':'honeycomb_CON.svg',
        'a'*120:'a'*80+'.svg',
    }
    for custom,expected in cases.items():
        r=client.post('/api/download/svg',json={'x':30,'y':30,'z':3,'filename':custom})
        assert r.status_code==200,r.text
        assert r.headers['content-disposition']==f'attachment; filename="{expected}"'
        assert re.fullmatch(r'attachment; filename="[A-Za-z0-9 _-]+\.svg"',r.headers['content-disposition'])

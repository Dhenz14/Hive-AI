# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

# Collect all hiveai package files
hiveai_root = os.path.join('..', 'hiveai')

a = Analysis(
    [os.path.join('..', 'hiveai', '__main__.py')],
    pathex=['..'],
    binaries=[],
    datas=[
        (os.path.join('..', 'hiveai', 'templates'), 'hiveai/templates'),
        (os.path.join('..', 'hiveai', 'static'), 'hiveai/static'),
    ],
    hiddenimports=[
        'hiveai',
        'hiveai.app',
        'hiveai.config',
        'hiveai.models',
        'hiveai.chat',
        'hiveai.hardware',
        'hiveai.lego_rebuild',
        'hiveai.llm',
        'hiveai.llm.client',
        'hiveai.pipeline',
        'hiveai.pipeline.orchestrator',
        'hiveai.pipeline.queue_worker',
        'hiveai.pipeline.crawler',
        'hiveai.pipeline.cleaner',
        'hiveai.pipeline.reasoner',
        'hiveai.pipeline.communities',
        'hiveai.pipeline.compressor',
        'hiveai.pipeline.writer',
        'hiveai.pipeline.publisher',
        'hiveai.pipeline.url_discovery',
        'hiveai.pipeline.entity_resolver',
        'hiveai.pipeline.contradiction',
        'hiveai.pipeline.graph_merger',
        'hiveai.pipeline.authority',
        'hiveai.pipeline.scorer',
        'hiveai.pipeline.hive_ping',
        'hiveai.pipeline.reembed',
        'flask',
        'sqlalchemy',
        'sqlalchemy.dialects.postgresql',
        'psycopg2',
        'pgvector',
        'pgvector.sqlalchemy',
        'sentence_transformers',
        'networkx',
        'instructor',
        'openai',
        'semchunk',
        'tenacity',
        'pydantic',
        'numpy',
        'gunicorn',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'PIL',
        'cv2',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='hiveai',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='hiveai',
)

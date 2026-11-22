#!/usr/bin/env python3
"""Archive the public Fifty Years Notion Content! page and linked resources."""
import json, re, time, sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
FILES = ROOT / 'presentations'
PAGE_ID = 'a06cf2ed-4c85-83f9-be50-81769ed802d7'
SPACE_ID = '3a50e3d8-1ca4-4efb-9098-9d3ce596d56e'
API = 'https://www.notion.so/api/v3/'
S = requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 (compatible; FiftyYearsArchive/1.0)'})

def post(endpoint, body):
    for attempt in range(6):
        r = S.post(API + endpoint, json=body, timeout=45)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(2 ** attempt, 30)); continue
        r.raise_for_status(); time.sleep(.15); return r.json()
    r.raise_for_status()

def get_page(pid):
    return post('loadCachedPageChunk', {'pageId':pid,'limit':100,'chunkNumber':0,'verticalColumns':False})

def block_value(record):
    return record.get('value',{}).get('value',{}) if isinstance(record,dict) else {}

def rich_text(value):
    if isinstance(value, list):
        parts=[]
        for x in value:
            if isinstance(x,str): parts.append(x)
            elif isinstance(x,list) and x and isinstance(x[0],str):
                parts.append(x[0])
                for ann in x[1:]:
                    if isinstance(ann,list) and len(ann)>1 and isinstance(ann[1],str): parts.append(f' <{ann[1]}>')
        return ''.join(parts)
    return str(value or '')

def props(block):
    out={}
    for k,v in (block.get('properties') or {}).items():
        out[k]=rich_text(v)
    return out

def main():
    DATA.mkdir(exist_ok=True); FILES.mkdir(exist_ok=True)
    initial=get_page(PAGE_ID)
    records={}; queue=[PAGE_ID]; seen=set(); views={}
    for table, recs in initial.get('recordMap',{}).items():
        if table=='block':
            for bid,rec in recs.items():
                b=block_value(rec)
                if b.get('type') and b.get('alive',True): records[bid]=b
        elif table=='collection_view':
            for vid,rec in recs.items():
                v=block_value(rec)
                if v.get('page_sort'):
                    views[vid]=v
                    queue.extend(v['page_sort'])
    for b in records.values(): queue.extend(b.get('content') or [])
    while queue:
        batch=[]
        while queue and len(batch)<40:
            pid=queue.pop(0)
            if pid not in seen:
                seen.add(pid)
                if pid not in records: batch.append(pid)
        if not batch: continue
        got=post('getRecordValues',{'requests':[{'id':pid,'table':'block'} for pid in batch]}).get('results',[])
        for pid,rec in zip(batch,got):
            b=rec.get('value') or {}
            if b.get('type') and b.get('alive',True):
                records[pid]=b
                queue.extend(b.get('content') or [])
        # Include row references from database view records. Child page content is loaded above.
    # Fetch any discovered record children missed because they were present in a parent response.
    # Also collect hierarchy and source data without lossy property simplification.
    ordered=[]
    for bid,b in records.items():
        item={'id':bid,'type':b.get('type'),'title':rich_text((b.get('properties') or {}).get('title',[])),
              'properties':props(b),'parent_id':b.get('parent_id'),'content':b.get('content',[]),'raw':b}
        ordered.append(item)
    (DATA/'notion-records.json').write_text(json.dumps({'source':f'https://fiftyyears.notion.site/content-c9','page_id':PAGE_ID,'views':{k:v for k,v in views.items()},'records':ordered},ensure_ascii=False,indent=2))
    # Human-readable page tree and database page properties.
    lines=['# Content! — Fifty Years','',f'Source: https://fiftyyears.notion.site/content-c9','',f'Archived records: {len(records)}','']
    for item in ordered:
        title=item['title'] or item['type'] or 'Untitled'
        lines += [f"## {title}",'',f"- Type: {item['type']}",f"- Notion ID: `{item['id']}`"]
        for k,v in item['properties'].items():
            if k!='title' and v: lines.append(f'- {k}: {v}')
        lines.append('')
    # Extract all YouTube URLs and attachment links from properties / content.
    blob=json.dumps(ordered,ensure_ascii=False)
    yt=sorted(set(re.findall(r'https?://(?:www\.)?(?:youtube\.com/watch\?[^\s"<>]+|youtu\.be/[^\s"<>]+)',blob)))
    metadata=[]
    for url in yt:
        try:
            r=S.get('https://www.youtube.com/oembed',params={'url':url,'format':'json'},timeout=30)
            r.raise_for_status(); data=r.json()
            metadata.append({'url':url,'title':data.get('title'),'author_name':data.get('author_name'),'thumbnail_url':data.get('thumbnail_url'),'provider_name':data.get('provider_name')})
        except Exception as e: metadata.append({'url':url,'title':None,'error':str(e)})
    (DATA/'youtube.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    (DATA/'youtube.csv').write_text('url,title,author_name\n'+''.join('"'+x['url'].replace('"','""')+'","'+str(x.get('title') or '').replace('"','""')+'","'+str(x.get('author_name') or '').replace('"','""')+'"\n' for x in metadata))
    attachments=[]; unique={}
    for item in ordered:
        b=item['raw']
        for key,val in (b.get('properties') or {}).items():
            s=json.dumps(val,ensure_ascii=False)
            # Native file references are attachment:<uuid>:<name>.
            for aid,name in re.findall(r'attachment:([0-9a-f-]{36}):([^"\\]+)',s,re.I):
                unique[(item['id'],aid,name)]=(item['id'],aid,name)
    for bid,aid,name in unique.values():
        rec={'page_id':bid,'attachment_id':aid,'name':name,'downloaded':False}
        try:
            signed=post('getSignedFileUrls',{'urls':[{'url':f'attachment:{aid}:{name}','permissionRecord':{'table':'block','id':bid}}]})['signedUrls'][0]
            safe=re.sub(r'[^A-Za-z0-9._ -]+','_',name).strip() or aid
            dest=FILES/safe
            if not dest.exists():
                rr=S.get(signed,timeout=90); rr.raise_for_status(); dest.write_bytes(rr.content)
            rec.update({'downloaded':True,'path':str(dest.relative_to(ROOT)),'bytes':dest.stat().st_size})
        except Exception as e: rec['error']=str(e)
        attachments.append(rec)
    (DATA/'attachments.json').write_text(json.dumps(attachments,ensure_ascii=False,indent=2))
    lines += ['## YouTube videos','']
    for v in metadata:
        title=v.get('title') or v['url']
        author=f" — {v['author_name']}" if v.get('author_name') else ''
        lines.append(f"- [{title}{author}]({v['url']})")
    lines += ['', '## Downloaded attachments', '']
    for a in attachments:
        label=a.get('name','attachment')
        if a.get('downloaded'): lines.append(f"- [{label}](../{a['path']})")
        else: lines.append(f"- {label} (download failed: {a.get('error','unknown error')})")
    lines.append('')
    (DATA/'content.md').write_text('\n'.join(lines))
    print(f'Archived {len(records)} Notion records, {len(yt)} YouTube links, {len(attachments)} attachments ({sum(x["downloaded"] for x in attachments)} downloaded).')

if __name__=='__main__': main()

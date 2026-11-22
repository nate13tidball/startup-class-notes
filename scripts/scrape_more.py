#!/usr/bin/env python3
"""Archive C9 Humans and Startup Perks; intentionally never fetch the calendar."""
import datetime as dt
import hashlib
import json
import re
import time
from collections import defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
API = 'https://www.notion.so/api/v3/'
PAGES = {
    'c9-humans': ('805cf2ed-4c85-83e5-912d-01c153be1f09', 'https://fiftyyears.notion.site/C9-Humans-805cf2ed4c8583e5912d01c153be1f09'),
    'startup-perks': ('200cf2ed-4c85-80a3-bfc6-e6a32a46cb62', 'https://fiftyyears.notion.site/5050-startup-perks-benefits'),
}
S = requests.Session()
S.headers['User-Agent'] = 'Mozilla/5.0 (compatible; FiftyYearsArchive/1.0)'


def post(name, body):
    for attempt in range(6):
        r = S.post(API + name, json=body, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(2 ** attempt, 30))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def unwrap(rec):
    return rec.get('value', {}).get('value', {}) if isinstance(rec, dict) else {}


def rich(value):
    if not isinstance(value, list):
        return str(value or '')
    out = []
    for part in value:
        if isinstance(part, str): out.append(part)
        elif isinstance(part, list) and part and isinstance(part[0], str):
            out.append(part[0])
            for annotation in part[1:]:
                if isinstance(annotation, list) and len(annotation) > 1 and isinstance(annotation[1], str):
                    out.append(f' <{annotation[1]}>')
    return ''.join(out)


def query_collection(collection_id, view_id, view):
    loader = {
        'type': 'reducer',
        'reducers': {
            'collection_group_results': {'type': 'results', 'limit': 100, 'loadContentCover': True},
            'table:uncategorized:title:count': {'type': 'aggregation', 'aggregation': {'property': 'title', 'aggregator': 'count'}},
        },
        'searchQuery': '',
        'userTimeZone': 'America/Los_Angeles',
    }
    loader.update(view.get('query2') or view.get('query') or {})
    return post('queryCollection', {'collection': {'id': collection_id}, 'collectionView': {'id': view_id}, 'loader': loader})


def get_page(pid):
    return post('loadCachedPageChunk', {'pageId': pid, 'limit': 100, 'chunkNumber': 0, 'verticalColumns': False})


def archive(label, page_id, source_url):
    outdir = ROOT / 'data' / label
    outdir.mkdir(parents=True, exist_ok=True)
    initial = get_page(page_id)
    records, views, collection_meta = {}, {}, {}
    queue = [page_id]

    def absorb(obj):
        for bid, rec in obj.get('recordMap', {}).get('block', {}).items():
            block = unwrap(rec)
            if block.get('type') and block.get('alive', True):
                records[bid] = block
                queue.extend(block.get('content') or [])
        for cid, rec in obj.get('recordMap', {}).get('collection', {}).items():
            collection_meta[cid] = unwrap(rec)
        for vid, rec in obj.get('recordMap', {}).get('collection_view', {}).items():
            view = unwrap(rec)
            if view:
                views[vid] = view

    absorb(initial)
    queried = set()
    seen = set()
    while queue:
        while queue:
            pid = queue.pop(0)
            if pid in seen: continue
            seen.add(pid)
            if pid not in records: break
        else:
            break
        batch = [pid]
        while queue and len(batch) < 40:
            other = queue.pop(0)
            if other not in seen:
                seen.add(other)
                if other not in records: batch.append(other)
        values = post('getRecordValues', {'requests': [{'id': pid, 'table': 'block'} for pid in batch]}).get('results', [])
        for pid, rec in zip(batch, values):
            block = rec.get('value') or {}
            if block.get('type') and block.get('alive', True):
                records[pid] = block
                queue.extend(block.get('content') or [])
        # Query any embedded database views once and queue all returned row pages.
        for block in list(records.values()):
            if block.get('type') not in {'collection_view', 'collection_view_page'}: continue
            cid = block.get('collection_id')
            for vid in block.get('view_ids') or []:
                key = (cid, vid)
                if not cid or key in queried or vid not in views: continue
                queried.add(key)
                result = query_collection(cid, vid, views[vid])
                absorb(result)
                rows = result.get('result', {}).get('reducerResults', {}).get('collection_group_results', {}).get('blockIds', [])
                queue.extend(x for x in rows if x not in seen)
    # Collection rows can include child-page IDs in view results; ensure every referenced record is fetched.
    for block in list(records.values()): queue.extend(x for x in block.get('content', []) if x not in seen)
    while queue:
        batch=[]
        while queue and len(batch)<40:
            pid=queue.pop(0)
            if pid not in seen:
                seen.add(pid)
                if pid not in records: batch.append(pid)
        if batch:
            vals=post('getRecordValues', {'requests':[{'id':pid,'table':'block'} for pid in batch]}).get('results',[])
            for pid,rec in zip(batch,vals):
                block=rec.get('value') or {}
                if block.get('type') and block.get('alive',True):
                    records[pid]=block; queue.extend(block.get('content') or [])
    items=[]
    field_names={}
    for collection in collection_meta.values():
        for property_id, definition in collection.get('schema', {}).items():
            field_names[property_id]=rich(definition.get('name'))
    for bid, block in records.items():
        items.append({'id':bid,'type':block.get('type'),'title':rich((block.get('properties') or {}).get('title',[])),
                      'properties':{field_names.get(key,key):rich(value) for key,value in (block.get('properties') or {}).items()},
                      'parent_id':block.get('parent_id'),'content':block.get('content',[]),'raw':block})
    (outdir/'notion-records.json').write_text(json.dumps({'source':source_url,'page_id':page_id,'records':items,
        'collections':collection_meta,'views':views},ensure_ascii=False,indent=2))
    # Resolve all attached Notion files in one signed-URL request.
    refs=[]
    for item in items:
        for value in (item['raw'].get('properties') or {}).values():
            for aid, name in re.findall(r'attachment:([0-9a-f-]{36}):([^"\\]+)', json.dumps(value,ensure_ascii=False), re.I):
                refs.append((item['id'], aid, name))
    refs=list(dict.fromkeys(refs))
    attdir=outdir/'attachments'; attdir.mkdir(exist_ok=True)
    attachments=[]
    for start in range(0,len(refs),50):
        batch=refs[start:start+50]
        try:
            urls=post('getSignedFileUrls', {'urls':[{'url':f'attachment:{aid}:{name}','permissionRecord':{'table':'block','id':bid}} for bid,aid,name in batch]}).get('signedUrls',[])
        except Exception as exc:
            attachments.extend({'page_id':bid,'attachment_id':aid,'name':name,'downloaded':False,'error':str(exc)} for bid,aid,name in batch)
            continue
        for (bid,aid,name),url in zip(batch,urls):
            safe=re.sub(r'[^A-Za-z0-9._ -]+','_',name).strip() or aid
            dest=attdir/safe
            record={'page_id':bid,'attachment_id':aid,'name':name,'downloaded':False}
            try:
                if not dest.exists():
                    r=S.get(url,timeout=90); r.raise_for_status(); dest.write_bytes(r.content)
                record.update(downloaded=True,path=str(dest.relative_to(ROOT)),bytes=dest.stat().st_size)
            except Exception as exc: record['error']=str(exc)
            attachments.append(record)
    (outdir/'attachments.json').write_text(json.dumps(attachments,ensure_ascii=False,indent=2))
    videos=[]
    blob=json.dumps(items,ensure_ascii=False)
    for url in sorted(set(re.findall(r'https?://(?:www\.)?(?:youtube\.com/watch\?[^\s"<>]+|youtu\.be/[^\s"<>]+)',blob))):
        try:
            r=S.get('https://www.youtube.com/oembed',params={'url':url,'format':'json'},timeout=30); r.raise_for_status(); data=r.json()
            videos.append({'url':url,'title':data.get('title'),'author_name':data.get('author_name')})
        except Exception as exc: videos.append({'url':url,'title':None,'error':str(exc)})
    (outdir/'youtube.json').write_text(json.dumps(videos,ensure_ascii=False,indent=2))
    lines=[f'# {label.replace("-"," ").title()}','',f'Source: {source_url}','',f'Archived records: {len(items)}','']
    for item in items:
        title=item['title'] or item['type'] or 'Untitled'
        lines += [f'## {title}','','- Type: '+str(item['type']),'- Notion ID: `'+item['id']+'`']
        for key,value in item['properties'].items():
            if key!='title' and value: lines.append(f'- {key}: {value}')
        lines.append('')
    if videos:
        lines += ['## YouTube videos','']
        lines += [f"- [{v.get('title') or v['url']}]({v['url']})" for v in videos]
    if attachments:
        lines += ['', '## Attachments','']
        lines += [f"- [{a['name']}]({a['path']})" if a.get('downloaded') else f"- {a['name']} (failed: {a.get('error')})" for a in attachments]
    (outdir/'content.md').write_text('\n'.join(lines)+'\n')
    return items, attachments


def human_contact_proposal(items):
    # Keep profile-level data and proposals in owner-only local state, never in Git.
    import sqlite3
    dbpath=Path('/srv/storage/repos/augment-wh-discovery-log-upper/data/discovery.sqlite3')
    if not dbpath.is_file(): raise RuntimeError(f'Canonical contact database unavailable: {dbpath}')
    with sqlite3.connect(f'file:{dbpath}?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        rows=[dict(row) for row in db.execute('SELECT contact_id,full_name,linkedin_url,affiliation,location FROM contacts WHERE linkedin_url IS NOT NULL AND trim(linkedin_url)<>""')]
    known=defaultdict(list)
    for row in rows: known[row['linkedin_url'].strip()].append(row)
    profiles=defaultdict(list)
    for item in items:
        p=item['properties']; name=p.get('Name','').strip(); link=p.get('LinkedIn','').strip()
        if name and link.startswith('http'): profiles[link].append((item,name,p))
    state=Path.home()/'.local/state/interaction-pipeline'; state.mkdir(mode=0o700,parents=True,exist_ok=True); state.chmod(0o700)
    now=dt.datetime.now().astimezone().isoformat(timespec='seconds'); events=[]; skipped=[]
    source='https://fiftyyears.notion.site/C9-Humans-805cf2ed4c8583e5912d01c153be1f09'
    for link, group in profiles.items():
        if len(group)>1 and len({x[1] for x in group})>1:
            skipped.append({'linkedin_url':link,'reason':'duplicate URL has conflicting names'}); continue
        item,name,p=group[0]
        if len(known.get(link,[]))>1:
            skipped.append({'name':name,'reason':'LinkedIn URL matches multiple existing contacts'}); continue
        contact=known[link][0] if known.get(link) else None
        if contact and contact['full_name'].strip().casefold()!=name.casefold():
            skipped.append({'name':name,'reason':'exact LinkedIn URL belongs to a differently named existing contact'}); continue
        data={'full_name':name,'linkedin_url':link}
        affiliation=p.get('Your current affiliation','').strip()
        location=p.get('Where are you based?','').strip()
        if affiliation: data['affiliation']=affiliation
        if location: data['location']=location
        if contact and all(str(contact.get(k) or '').strip()==str(v).strip() for k,v in data.items()):
            skipped.append({'name':name,'reason':'already present with the same profile fields'}); continue
        norm=link.strip()
        source_key=hashlib.sha256(('notion-c9-human\0'+norm).encode()).hexdigest()
        contact_id=contact['contact_id'] if contact else 'contact:manual-'+hashlib.sha256(norm.encode()).hexdigest()[:20]
        data['extensions']={'codex_capture':{'source_kind':'notion-cohort-directory','source_key':source_key}}
        events.append({'event_id':'evt_'+hashlib.sha256((source_key+'\0'+contact_id).encode()).hexdigest()[:32],
            'schema_version':2,'event_type':'contact.profile_recorded','occurred_at':now,'recorded_at':now,
            'actor':'nathan','source':'codex-manual-import','subject':{'type':'contact','id':contact_id},'data':data,
            'evidence':[{'ref':source,'label':'C9 Humans Notion directory row '+item['id']}],'correction_of':None})
    path=state/'c9-humans-contact-proposal.json'
    path.write_text(json.dumps(events,ensure_ascii=False,indent=2)+'\n'); path.chmod(0o600)
    return path, len(profiles), events, skipped


def main():
    human_items, human_files=archive('c9-humans',*PAGES['c9-humans'])
    perks_items, perks_files=archive('startup-perks',*PAGES['startup-perks'])
    proposal,total,events,skipped=human_contact_proposal(human_items)
    print(f'C9 Humans: {len(human_items)} Notion records, {total} named LinkedIn profiles considered, {len(events)} import events proposed, {len(skipped)} skipped/review, {len(human_files)} attachments.')
    print(f'Startup perks: {len(perks_items)} Notion records, {len(perks_files)} attachments.')
    print(f'Contact proposal: {proposal} (preview only; not applied).')
    if skipped:
        counts=defaultdict(int)
        for row in skipped: counts[row['reason']]+=1
        print('Skipped categories:',dict(counts))

if __name__=='__main__': main()

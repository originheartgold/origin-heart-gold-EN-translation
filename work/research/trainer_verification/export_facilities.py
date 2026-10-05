"""Inventory local CN facility pools; no downloads, writes only ignored output.
16-byte candidate schema cross-checked with public battle-factory-editor-hgss
parse_a203; pool memberships with parse_a202. Runtime evidence is recorded separately in facilities_runtime.json; this file preserves the raw inventory.
"""
import collections,hashlib,json,struct
from pathlib import Path
import ndspy.rom,ndspy.narc
SOURCE=Path(__file__).resolve().parents[3]
OUT=SOURCE/'work/build/difficulty-trainers-v3';OUT.mkdir(parents=True,exist_ok=True)
CN=ndspy.rom.NintendoDSRom.fromFile(str(SOURCE/'work/rom/origin_v4.0.3_cn.nds'))
US=ndspy.rom.NintendoDSRom.fromFile(str(SOURCE/'work/rom/Pokemon - HeartGold Version (USA).nds'))
# Independent NARC table reader, rather than trusting ndspy indexing twice.
def direct(raw):
 assert raw[:4]==b'NARC'
 off=struct.unpack_from('<H',raw,12)[0];chunks={}
 for _ in range(struct.unpack_from('<H',raw,14)[0]):
  tag=bytes(raw[off:off+4]);size=struct.unpack_from('<I',raw,off+4)[0];chunks[tag]=raw[off:off+size];off+=size
 fat=chunks[b'BTAF'];body=chunks[b'GMIF'][8:];count=struct.unpack_from('<H',fat,8)[0]
 return [body[a:b] for a,b in [struct.unpack_from('<II',fat,12+i*8) for i in range(count)]]
def archive(path):
 raw=CN.getFileByName(path);fs=[bytes(x) for x in ndspy.narc.NARC(raw).files];assert fs==direct(raw)
 us=US.getFileByName(path);ufs=direct(us)
 return fs,dict(path=path,members=len(fs),sha256=hashlib.sha256(raw).hexdigest(),us_archive_identical=raw==us,us_members=len(ufs),changed_member_ids=[i for i,x in enumerate(fs) if i>=len(ufs) or x!=ufs[i]])
pools={};trainers={};summaries=[]
for path in ['a/1/2/9','a/2/0/3','a/2/0/4']:
 fs,summary=archive(path);rows=[]
 for i,b in enumerate(fs):
  assert len(b)==16
  s,*other=struct.unpack('<5HBBHH',b)
  moves=other[:4];ev,nature,item,form=other[4:]
  assert 0<=nature<25 and 0<=ev<64
  rows.append(dict(id=i,species=s,moves=moves,ev_mask=ev,nature=nature,item=item,form_candidate=form,raw_hex=b.hex(),level=None,ivs=None,ability=None,runtime_parameters='not present in this static record'))
 summary.update(nonzero_species_records=sum(bool(x['species']) for x in rows),species_count=len({x['species'] for x in rows if x['species']}),max_species=max(x['species'] for x in rows),max_move=max(m for x in rows for m in x['moves']))
 summaries.append(summary);pools[path]=rows
for path,monpath in [('a/1/2/8','a/1/2/9'),('a/2/0/2','a/2/0/3')]:
 fs,summary=archive(path);rows=[]
 for i,b in enumerate(fs):
  cls,count=struct.unpack_from('<HH',b)
  assert len(b)==((4+2*count+3)//4)*4
  ids=list(struct.unpack_from('<'+'H'*count,b,4));assert all(0<=v<len(pools[monpath]) for v in ids)
  rows.append(dict(id=i,trainer_class=cls,pool_size=count,pool_ids=ids,pool_archive=monpath,padding_hex=b[4+2*count:].hex(),raw_hex=b.hex(),selection_policy='unresolved',level_policy='unresolved',name_mapping='unresolved; separate ID namespace from story trainer archive'))
 summary.update(pool_memberships=sum(x['pool_size'] for x in rows),unique_referenced_sets=len({i for x in rows for i in x['pool_ids']}))
 summaries.append(summary);trainers[path]=rows
out=dict(schema_version=1,scope='facility archive inventory; runtime routing/selection not verified',summaries=summaries,pokemon_pools=pools,trainer_pools=trainers,source_reference='https://github.com/MichaelFacci/battle-factory-editor-hgss/blob/main/battle_factory_editor_v3.2.py',not_claimed=['every facility archive located','facility-name mapping','generated battle levels or IVs','story trainer IDs707-711 linked to pools','all possible team combinations enumerated'])
out['provenance'] = dict(cn_rom_sha256=hashlib.sha256((SOURCE/'work/rom/origin_v4.0.3_cn.nds').read_bytes()).hexdigest(), us_rom_sha256=hashlib.sha256((SOURCE/'work/rom/Pokemon - HeartGold Version (USA).nds').read_bytes()).hexdigest(), exporter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
p=OUT/'facilities.json.tmp';p.write_text(json.dumps(out,indent=2)+'\n');p.replace(OUT/'facilities.json')
print(json.dumps(summaries,indent=2))
print('PASS: all NARC members independently re-read, all species-set lengths and nature/EV bounds checked, all trainer pool lengths and memberships checked')

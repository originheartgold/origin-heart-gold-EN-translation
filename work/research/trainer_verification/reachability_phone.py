"""Original-ROM phone rematch table references, distinguished from active callers."""
import json
import struct
from pathlib import Path
import ndspy.rom
from work.research.trainer_verification import reachability as R


def build(ctx):
    rom = ndspy.rom.NintendoDSRom.fromFile(ctx.rom.path)
    ov = rom.loadArm9Overlays([27])[27]
    data = bytes(ov.data)
    read = lambda address, length: data[address-ov.ramAddress:address-ov.ramAddress+length]
    assert struct.unpack_from('<I', ctx.rom.arm9, 0xF793C + 142*4)[0] == 0x02041F69
    assert ctx.rom.a9(0x02041FD4, 4) == struct.pack('<I', 27)
    assert read(0x0225C00C, 4) == struct.pack('<I', 0x0225C1CC)
    assert read(0x0225C004, 2) == bytes.fromhex('3f2a')  # compare row counter with63
    assert read(0x0225C0CC, 4) == struct.pack('<I', 0x0225C1CC)
    rows = [list(struct.unpack('<6H', read(0x0225C1CC + i*12,12))) for i in range(63)]
    book = bytes(rom.getFileByName('tel/pmtel_book.dat'))
    count = struct.unpack_from('<I', book)[0]
    assert len(book) == 4+20*count
    contacts = [dict(contact_id=i, base_trainer_id=struct.unpack_from('<H',book,4+i*20+4)[0]) for i in range(count)]
    by_base = {row[0]:row for row in rows}
    objects=[]
    for zone in ctx.zones:
        for obj in ctx.events[zone['events_bank']]['obj']:
            sid=obj['script']
            if 3000<=sid<7000:
                objects.append(dict(zone=zone['zone_id'],object_id=obj['id'],base_trainer_id=sid-(2999 if sid<5000 else 4999)))
    fixed=[]
    direct_trainer_std=[]
    for f,d in ctx.S.items():
        for pc,(op,args,_n,_t) in d['ins'].items():
            if op==142:
                fixed.append(dict(script=f,pc=pc,contact_operand=args[0],contact_id=args[0] if args[0]<0x4000 else None))
            if op in (19,20) and 3000<=args[0]<7000:
                direct_trainer_std.append(dict(script=f,pc=pc,script_id=args[0]))
    object_bases={o['base_trainer_id'] for o in objects}
    fixed_contacts={x['contact_id'] for x in fixed if x['contact_id'] is not None}
    candidates=[]
    for contact in contacts:
        base=contact['base_trainer_id']
        if base not in by_base:continue
        row=by_base[base]
        for stage,tid in enumerate(row):
            if tid in (0,65535):continue
            candidates.append(dict(**contact,stage=stage,trainer_id=tid,map_object_caller_found=base in object_bases,explicit_contact_caller_found=contact['contact_id'] in fixed_contacts,feasibility='unproven'))
    _,parties=R.G.load_trainers(ctx)
    loc=R.G.trainer_locations(ctx)
    unref={i for i,p in enumerate(parties) if p and i not in loc}
    referenced=unref&{t for row in rows for t in row if t not in (0,65535)}
    active_candidates={c['trainer_id'] for c in candidates if c['map_object_caller_found'] or c['explicit_contact_caller_found']}
    return dict(summary=dict(table_rows=len(rows),contacts=count,encounter_unreferenced_with_table_reference=sorted(referenced),encounter_unreferenced_with_caller_candidate=sorted(unref&active_candidates),remaining_without_fixed_or_phone_table_reference=sorted(unref-referenced)),rows=rows,contacts=contacts,candidates=candidates,command_calls=fixed,direct_trainer_standard_calls=direct_trainer_std)

if __name__=='__main__':
    result=build(R.G.Ctx())
    out=Path('work/build/trainer_verification/reachability/phone_supplement.json')
    out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['summary'],indent=2))

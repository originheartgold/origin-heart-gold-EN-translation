"""Source-guarded facility field interpretation for the untouched Chinese ROM.

Run from repository root with .venv/bin/python. Outputs are ignored research
artifacts, not game data for publication. This is a static code audit, not an
emulator test or complete facility reachability/selection proof.
"""
import hashlib,json,struct
from pathlib import Path
import ndspy.narc
from facilities_disasm import load,OUT
REGIONS = [
('arm9', 33585144, 33585292, 'b605ce3d67e95cdb70a8d38fbe700f9426421a539bddb78e63fe33619b5c5a69'),
('arm9', 33860080, 33860140, 'cd44e2f2ffb92919a92bd8f82f36daba400cd0d61d97114e9d330d99fcd0f0ba'),
('arm9', 33860944, 33861396, '6949fb26d6945f57efd9e6c656d51b7991604408e12b72b5d1887212fbc2f899'),
('arm9', 33861580, 33862056, '713ffb020eb5c10d2344d3a8d0167564071a131ddecb02bf688ee84089a07797'),
('arm9', 34009568, 34009582, '862f7a2517041817ac1acc79d1b7532d2686f1ec194de9d26099b5e03e852269'),
('arm9', 34010156, 34010200, 'c6e88bed5bef082f4bf490db42b61e28a87bb088b9205f5af2268f53bc023f99'),
('ov77', 35807040, 35808096, '818a94720629c9f06ab75a04ec38802fb30451785e7d8a156da0813450662430'),
('ov77', 35808576, 35809312, 'af4e58e9c1d9760c8da87198f2eeec1097e98427785ccdbab0e8675bc9959b3a'),
('ov77', 35857344, 35859168, '170405ad349d48166cf8f4cfc696f9b32a0800e4a2338fc27a88f00f7ac3c998'),
('ov77', 35860620, 35860636, '59b938429771f5e9e7404e4928f92ff37756ce27168b74cb3c994b88f0fdcd4c'),
('ov77', 35862086, 35862132, '87334d5efeeb6c33138f8837360a06f7cf03250234380fd42dbb4e85dd683804'),
('ov77', 35862524, 35862760, '64bf26d52c5a405f4bfec4f3083225f7fb039f164236007f9088f867c38842d4'),
('arm9', 33723660, 33723664, 'e7d33b9d94bc21a025f4e297bd111d93fc82dda4e64e86141585162232b0d2bc'),
('arm9', 33839796, 33839964, 'fe8d836bc626a5648fb509749ccb3cf00cddcfad3ca89e3868d9320e38da98f1'),
('arm9', 34167740, 34167840, '7eeac112f5c5ad103cbb0e357e513007f1634612ef16e974da7b2993e4977add'),
('ov77', 35809440, 35809548, '7e933dad7c2c1c722c4c9e7c70fe682e0c12b51c63bef2ffb5d3f4b3717743e5'),
('ov77', 35809940, 35809998, '4f9306d08843c20f74c5fa0a5620ffa8ebe5222441bde418680e926e98b302d3'),
('ov77', 35810548, 35810800, '0cc4dd8eeced454d706e985e36718469dbf5bafc56da188e6ba62eb5c4b93f70'),
('ov77', 35820476, 35820524, 'cf88efbd993455514946c33fe998669e6d5a9cfd7555bc1d38ee7f218e172d49'),
('ov77', 35829104, 35829196, '70616ec67bc7a2295df1023f9c1850ea2e11e122637ecb9ec26b4cd00fbd45a8'),
('ov77', 35830892, 35831380, 'e75e0562f47524612f18107923be8da19133f189f4dd7edd2f1ba941cbe64708'),
('ov77', 35831380, 35831474, '52054a5dc6d25913a03cba07e75fca427d86240debc45c9c2131c2a581b780db'),
('ov77', 35859424, 35859960, 'e32ca3fbd29d9279d12cd2cddf132d8543b2871933a9072fa800de253ef48d25'),
('ov77', 35860636, 35860764, 'e781ffab54260693922ca87cc8125c3f6abd663d0f8e8e2e4a52be2e0c984bc8'),
('ov77', 35878524, 35878724, 'ebd78cdfe8f1945aed7c7e98125acd20b73a01105f4db2a75c0b9f2784fb7019'),
('ov77', 35882060, 35882220, '8eff6499d4cb65ee97e0f64d8d336677d77c27c328c39e008e7ad79c9b6a62e3'),
]
ARCHIVES={128:'a/1/2/8',129:'a/1/2/9',204:'a/2/0/2',205:'a/2/0/3',206:'a/2/0/4'}
def evs(mask):
    """Result bytes of reviewed constructor; zero mask writes no EV bytes.

    Do not interpret the zero case as emulation of the divide-by-zero helper.
    The cleared output and absent selected bits establish zero output EVs.
    """
    if not 0 <= mask < 64: raise ValueError('six-bit EV mask required')
    value=min(255,510//mask.bit_count()) if mask else 0
    return [value if mask&(1<<i) else 0 for i in range(6)]
def verify():
    r,images=load();guards=[]
    for name,a,b,wanted in REGIONS:
        base,data=images[name];got=hashlib.sha256(data[a-base:b-base]).hexdigest()
        if got!=wanted: raise ValueError(f'Unreviewed runtime: {name} {a:#x}')
        guards.append(dict(image=name,start=hex(a),end_exclusive=hex(b),sha256=got))
    remaps=[struct.unpack_from('<3H',r.arm9,0xf233c+6*i) for i in range(12)]
    for archive_id,path in ARCHIVES.items():
        ptr=struct.unpack_from('<I',r.arm9,0x10e21c+archive_id*4)[0]-r.arm9RamAddress
        actual=bytes(r.arm9[ptr:r.arm9.index(0,ptr)]).decode()
        if actual!=path: raise ValueError(f'Archive route changed: {archive_id}')
        if archive_id in [x[0] for x in remaps]:raise ValueError('Facility archive now remapped')
    script_guards=[]
    for path,member,wanted in [('a/0/1/2',84,'58b81ec69675b6e94a1611420f2d19d77006f6332de9796cbc9c7afd3a30ed84'),('a/1/8/2',1,'05e0d8157b52194814febca2a4254b6c879192b7818959aaa347e4aaf08e61b2')]:
        got=hashlib.sha256(ndspy.narc.NARC(r.getFileByName(path)).files[member]).hexdigest()
        if got!=wanted: raise ValueError('Unreviewed Factory script')
        script_guards.append(dict(archive=path,member=member,sha256=got))
    rows={};counts={}
    for path in ('a/1/2/9','a/2/0/3','a/2/0/4'):
        members=ndspy.narc.NARC(r.getFileByName(path)).files;out=[]
        for i,b in enumerate(members):
            if len(b)!=16:raise ValueError('Unreviewed record size')
            form=struct.unpack_from('<H',b,14)[0]
            out.append(dict(id=i,stored_form_word=form,form=form&31,
                ev_mask=b[10],evs_storage_order=evs(b[10]),
                evs_display_order=[evs(b[10])[j] for j in (0,1,2,4,5,3)],
                stored_nature=b[11],stored_item=struct.unpack_from('<H',b,12)[0]))
        rows[path]=out
        counts[path]=dict(records=len(out),nonzero_forms=sum(x['form']!=0 for x in out),
            zero_ev_mask_ids=[x['id'] for x in out if x['ev_mask']==0])
    result=dict(schema_version=1,scope='static runtime evidence, partial routing and selection audit',
        named_factory_example={'map_zone':275,'field_script':84,'field_script_launch_pc':'0x411','field_command':627,'application_id':3,'runtime_script_archive':'a/1/8/2','runtime_script_member':1,'runtime_init_pc':'0x34c','runtime_init_opcode':92,'state_initializer':'ov77:0x0222BC6C','level_selector':'ov77:0x0223308C','level_menu_mapping':{'0':50,'1':100},'rental_sampler':'ov77:0x02232C04','stage_zero_no_upgrade':{'level50':{'set_ids_inclusive':[1,150],'ivs_all_six':0},'open_level':{'set_ids_inclusive':[351,486],'ivs_all_six':0}},'scope':'static menu/state/dataflow proof, no emulator replay'},
        reviewed_legacy_route={'selector':'ov77:0x02232A98','participant_getter':'arm9:0x0202950C','getter_patched_constant':7,'result':1,'selected_trainer_archive':204,'selected_set_archive':205,'caveat':'conditional on participant retrieval/assertions completing for modes3/6; does not prove all legacy archives unreachable from every caller'},
        source_rom_sha256=hashlib.sha256(Path('work/rom/origin_v4.0.3_cn.nds').read_bytes()).hexdigest(),
        guards=guards,script_guards=script_guards,archive_ids=ARCHIVES,counts=counts,pokemon_field_interpretations=rows,
        verified=['form is low five bits of record u16 at offset 14',
          'EV mask expands in HP/Atk/Def/Speed/SpAtk/SpDef order',
          'generated PID is nature-constrained and non-shiny; supplied PID bypasses this loop',
          'ability chosen from base-species ability fields 24/25 using PID parity',
          'IV input repeated across all six stats; ordinary trainer HP-IV override not used',
          'stored items may be replaced by caller-enabled four-item fallback',
          'separate sampler policies exist; see report'],
        constructor_scope={'routine':'ov77:0x02225FCC','materializer':'ov77:0x02226194','archive_inputs':[129,205,206], 'archive_inputs_scope':'static constructor support; legacy129 not selected on the reviewed patched route', 'level_ivs_pid_and_item_override':'caller-supplied, not fixed by static set'},
        selection_callers=[{'routine':'arm9:0x0204AFCC / ov77:0x02232414','reference_model':'legacy_candidate','verified':'species exclusion retained; after 50 item conflicts item exclusions relaxed and fallback items enabled','facility_mode_mapping':'partial'},
          {'routine':'ov77:0x02226634','reference_model':'shared_candidate','verified':'internal species/item exclusions retained including zero; after 50 external conflicts only external exclusions relaxed','facility_mode_mapping':'unresolved'}],
        unresolved=['complete mode-to-facility-name dispatch proof',
          'all trainer/set selection ranges and weights for every facility mode',
          'all caller-supplied level, IV, forced PID and item-override values',
          'complete dynamic event/item modifications after materialization',
          'emulator replay of all facility modes'])
    OUT.mkdir(parents=True,exist_ok=True)
    dest=OUT/'runtime_verified.json';tmp=dest.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(result,indent=2)+'\n');tmp.replace(dest)
    print(json.dumps(dict(code_guards=len(guards),counts=counts,report=str(dest)),indent=2))
    return result
if __name__=='__main__':verify()

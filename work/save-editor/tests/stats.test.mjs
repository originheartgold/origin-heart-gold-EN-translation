import test from 'node:test';
import assert from 'node:assert/strict';
import { calculateStats, adjustCurrentHp, validateStatValues, experienceForLevel } from '../dist/core/stats.js';
const values = value => ({hp:value, attack:value, defense:value, speed:value, spAttack:value, spDefense:value});

test('IV and EV limits reject invalid numbers, missing fields and total over 510', () => {
  validateStatValues(values(31), 'IV');
  validateStatValues({...values(0), hp:255, speed:255}, 'EV');
  for (const invalid of [-1, 32, 1.5, NaN, Infinity, '1']) {
    assert.throws(() => validateStatValues({...values(0), hp:invalid}, 'IV'));
  }
  assert.throws(() => validateStatValues({...values(0), hp:256}, 'EV'));
  assert.throws(() => validateStatValues({...values(0), hp:255, speed:255, attack:1}, 'EV'));
  assert.throws(() => validateStatValues({hp:0}, 'IV'));
  assert.throws(() => validateStatValues({...values(0), extra:0}, 'IV'));
});

test('floor EV contribution before level scaling and floor nature after scaling', () => {
  const stats = calculateStats([57,71,83,97,109,127], values(17), {...values(3), attack:7}, 37, 1, 42);
  assert.deepEqual(stats, {hp:95,attack:70,defense:64,speed:83,spAttack:91,spDefense:105});
});

// Explicit independent nature mapping: Attack, Defense, Speed, SpAtk, SpDef.
const effects = [[-1,-1],[0,1],[0,2],[0,3],[0,4],[1,0],[-1,-1],[1,2],[1,3],[1,4],
  [2,0],[2,1],[-1,-1],[2,3],[2,4],[3,0],[3,1],[3,2],[-1,-1],[3,4],
  [4,0],[4,1],[4,2],[4,3],[-1,-1]];
for (let nature = 0; nature < 25; nature++) {
  test(`nature ${nature} applies only its two modifiers`, () => {
    const result = calculateStats([50,50,50,50,50,50], values(0), values(0), 50, nature, 1);
    const other = ['attack','defense','speed','spAttack','spDefense'].map(key => result[key]);
    assert.equal(result.hp,110);
    assert.deepEqual(other, [0,1,2,3,4].map(i => i === effects[nature][0] ? 60 : i === effects[nature][1] ? 49 : 55));
  });
}

test('Shedinja HP remains one and native maximum-stat nature multiplication wraps u16', () => {
  assert.equal(calculateStats([1,50,50,50,50,50],values(31),values(0),100,0,292).hp,1);
  const stats = calculateStats([255,255,255,255,255,255],values(31),{...values(0),attack:252},100,1,1);
  assert.equal(stats.attack,14); // (609 * 110) narrowed to uint16 = 1454.
});

test('HP changes reproduce native increase, decrease, fainted and initialization branches', () => {
  assert.equal(adjustCurrentHp(30,100,110,1),40);
  assert.equal(adjustCurrentHp(30,100,90,1),30);
  assert.equal(adjustCurrentHp(95,100,90,1),90);
  assert.equal(adjustCurrentHp(0,100,110,1),0);
  assert.equal(adjustCurrentHp(0,0,110,1),110);
  assert.equal(adjustCurrentHp(1,1,1,292),1);
  assert.equal(adjustCurrentHp(0,1,1,292),0);
  assert.equal(adjustCurrentHp(0,0,1,292),1);
});

test('exact local ROM growth thresholds required; no guessed growth curves', () => {
  const synthetic = Array.from({length:101},(_,level) => level < 2 ? 0 : level * 123);
  assert.equal(experienceForLevel(1,0,synthetic),0);
  assert.equal(experienceForLevel(50,7,synthetic),6150);
  assert.equal(experienceForLevel(100,3,synthetic),12300);
  assert.throws(() => experienceForLevel(50,0));
  for (const level of [0,101,1.5,NaN]) assert.throws(() => experienceForLevel(level,0,synthetic));
  assert.throws(() => experienceForLevel(50,8,synthetic));
  for (const invalid of [synthetic.slice(1), synthetic.map((x,i) => i===1 ? 1:x), synthetic.map((x,i) => i===50 ? NaN:x), synthetic.map((x,i) => i===50 ? 1:x)]) {
    assert.throws(() => experienceForLevel(50,0,invalid));
  }
});

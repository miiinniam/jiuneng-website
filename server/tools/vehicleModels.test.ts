/**
 * 车型库映射（契约 §A）
 * ────────────────────────────────────────────────────────────
 * 只测纯函数 `mapCatalogue`（不碰网络、不打引擎）。钉住四件事：
 *  1. 一行库记录映射出全部字段，数值/文本原样；
 *  2. 缺字段 / 非法值：可空的 6 个走 `null`，必填的 4 个走 `0`，货类只收字符串；
 *  3. Map 的 key 是 `model_id`，`category` 取外层键（引擎带空类别空数组也要跳过）；
 *  4. **成本单价与 `notes` 在任何输出里都不存在**（白名单重建，不是删键）。
 *
 * 跑法：node --test server/tools/vehicleModels.test.ts
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { mapCatalogue } from './vehicleModels.ts';

/** 引擎实测回包的一行（含 31 列里的 6 个禁出字段 + 无关列 osrm_profile / volume_capacity_m3）。 */
const ROW_FULL = {
  model_id: 'flatbed_low_17m5',
  display_name: '低平板 17.5 米',
  max_load_ton: 38,
  volume_capacity_m3: 0,
  length_m: 17.5,
  width_m: 3,
  height_m: 1.2,
  max_cargo_height_m: 3.2,
  loading_efficiency: 0.9,
  curb_weight_ton: 15,
  floor_area_m2: 52.5,
  effective_volume_m3: 168,
  base_rate_vnd_per_km: 99999,
  fuel_l_per_100km: 40,
  fuel_penalty: 0,
  fixed_surcharge_vnd: 1,
  toll_rate_vnd_per_km: 1,
  osrm_profile: 'driving',
  axle_config: 'TR-02',
  suitable_cargo_types: ['normal', 'other'],
  notes: '供应商备注：可伸缩宽 3.4m，需提前 1 天报备',
};

const RAW = {
  flatbed: [ROW_FULL],
  small_box: [],
  container: [
    // 缺一半字段 + 若干非法值
    {
      model_id: 'container_45hc',
      display_name: '45HC 集装箱车',
      max_load_ton: null,
      length_m: '13.5',
      width_m: '很宽',
      height_m: undefined,
      max_cargo_height_m: 'NaN',
      loading_efficiency: null,
      curb_weight_ton: '',
      floor_area_m2: true,
      effective_volume_m3: { value: 104 },
      axle_config: '   ',
      suitable_cargo_types: ['normal', '', 42, ' normal ', null, 'cold'],
      base_rate_vnd_per_km: 123456,
      notes: '这条也不许出现在输出里',
    },
    // 垃圾行：缺 model_id / 非对象 —— 一律跳过，不许造 key
    { display_name: '没有 id 的车' },
    null,
    'oops',
  ],
  // 非数组的类别值：跳过
  cold_chain: { model_id: 'x' },
};

/** `JSON.stringify(Map)` 恒为 `{}`，所以展开成对象再序列化才有意义。 */
const dump = (map: Map<string, unknown>): string => JSON.stringify(Object.fromEntries(map));

test('正常一行映射出全部字段（13 个库字段 + category）', () => {
  const map = mapCatalogue({ flatbed: [ROW_FULL] });
  assert.equal(map.size, 1);
  const spec = map.get('flatbed_low_17m5');
  assert.ok(spec);
  if (!spec) return;

  // 键集白名单：多一个都不行（成本列、notes、osrm_profile、volume_capacity_m3 都不在里面）
  assert.deepEqual(Object.keys(spec).sort(), [
    'axle_config',
    'category',
    'curb_weight_ton',
    'display_name',
    'effective_volume_m3',
    'floor_area_m2',
    'height_m',
    'length_m',
    'loading_efficiency',
    'max_cargo_height_m',
    'max_load_ton',
    'model_id',
    'suitable_cargo_types',
    'width_m',
  ]);

  assert.equal(spec.model_id, 'flatbed_low_17m5');
  assert.equal(spec.display_name, '低平板 17.5 米');
  assert.equal(spec.category, 'flatbed');
  assert.equal(spec.max_load_ton, 38);
  assert.equal(spec.length_m, 17.5);
  assert.equal(spec.width_m, 3);
  assert.equal(spec.height_m, 1.2);
  assert.equal(spec.max_cargo_height_m, 3.2);
  assert.equal(spec.loading_efficiency, 0.9);
  assert.equal(spec.curb_weight_ton, 15);
  assert.equal(spec.floor_area_m2, 52.5);
  assert.equal(spec.effective_volume_m3, 168);
  assert.equal(spec.axle_config, 'TR-02');
  assert.deepEqual(spec.suitable_cargo_types, ['normal', 'other']);
});

test('缺字段 / 非法值：可空 6 个走 null，必填 4 个走 0，货类只收字符串', () => {
  const map = mapCatalogue(RAW);
  const spec = map.get('container_45hc');
  assert.ok(spec, '数字字符串 length_m 与合法 model_id 的行必须保留');
  if (!spec) return;

  // 必填数值：取不到记 0
  assert.equal(spec.max_load_ton, 0, 'null → 0');
  assert.equal(spec.length_m, 13.5, '数字字符串要收');
  assert.equal(spec.width_m, 0, '非数字字符串 → 0');
  assert.equal(spec.height_m, 0, 'undefined → 0');

  // 可空数值：取不到/非法一律 null（不许编 0）
  assert.equal(spec.max_cargo_height_m, null);
  assert.equal(spec.loading_efficiency, null);
  assert.equal(spec.curb_weight_ton, null, '空串 → null');
  assert.equal(spec.floor_area_m2, null, 'bool 不算数值');
  assert.equal(spec.effective_volume_m3, null, '对象不算数值');
  assert.equal(spec.axle_config, null, '纯空白 → null');

  // 货类：只留字符串、trim、去空去重
  assert.deepEqual(spec.suitable_cargo_types, ['normal', 'cold']);
});

test('Map 的 key 是 model_id，category 取外层键；垃圾行与空类别跳过', () => {
  const map = mapCatalogue(RAW);
  assert.deepEqual([...map.keys()].sort(), ['container_45hc', 'flatbed_low_17m5']);
  assert.equal(map.get('flatbed_low_17m5')?.category, 'flatbed');
  assert.equal(map.get('container_45hc')?.category, 'container');
  assert.equal(map.has('没有 id 的车'), false, '缺 model_id 不许造 key');
  assert.equal(map.size, 2, '空数组类别 / 非数组类别 / 非对象行都不进表');

  // 回包整体形状不对时：空 Map，不抛
  for (const bad of [null, undefined, 'oops', 42, [] as unknown]) {
    assert.equal(mapCatalogue(bad).size, 0);
  }
});

test('成本单价与 notes 在任何输出里都不存在（白名单重建）', () => {
  const map = mapCatalogue(RAW);
  const json = dump(map);
  for (const forbidden of [
    'base_rate_vnd_per_km',
    'fuel_l_per_100km',
    'fuel_penalty',
    'fixed_surcharge_vnd',
    'toll_rate_vnd_per_km',
    'notes',
    // 非成本但同样不该出现的引擎列
    'osrm_profile',
    'volume_capacity_m3',
    // 备注的正文也不许漏出来（防止有人日后改成 spread 后删键）
    '供应商备注',
    '99999',
    '123456',
    '40',
  ]) {
    assert.equal(json.includes(forbidden), false, `输出泄漏了 ${forbidden}`);
  }

  // 再逐个对象核一遍键集（序列化断言之外的第二道闸）
  const banned = new Set([
    'base_rate_vnd_per_km',
    'fuel_l_per_100km',
    'fuel_penalty',
    'fixed_surcharge_vnd',
    'toll_rate_vnd_per_km',
    'notes',
  ]);
  for (const spec of map.values()) {
    for (const key of Object.keys(spec)) {
      assert.equal(banned.has(key), false, `VehicleSpec 出现了禁出字段 ${key}`);
    }
  }
});

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildPlan } from './plan.ts';
import type { PublicQuoteResult } from '../../api';
import type { QuoteFormState } from '../../engine/types';

const form = {
  originLat: '22.1000',
  originLng: '106.7500',
  originLabel: '广西 凭祥 友谊关',
  destLat: '21.0300',
  destLng: '105.8500',
  destLabel: '河内 还剑郡',
  waypoints: [],
  weightKg: '25',
  weightUnit: 'ton',
  volumeM3: '40',
  cargoType: 'normal',
  cargoValueVnd: '',
  items: [],
  loadingMode: 'full_truck',
  vehicleModelId: 'flatbed_13m',
  emptyReturn: false,
  needLoading: false,
  avoidRestrictedZones: false,
  avoidConstructionZones: false,
  viaMountainRoad: false,
  fuelPriceVnd: '',
  wageHourlyVnd: '',
  tollRateVndPerKm: '',
  miscCostVnd: '',
} as unknown as QuoteFormState;

const publicResult: PublicQuoteResult = {
  ok: true,
  scope: 'public',
  distance_km: 302.8,
  duration_h: 5.5,
  vehicle_count: 1,
  vehicle: { id: 'flatbed_13m', name: '普通平板 13米', max_load_ton: 26 },
  price_low_vnd: null,
  price_high_vnd: null,
  timing: { loading_hours: 0, rest_hours: 0, total_duration_h: 5.5 },
  geometry: null,
};

test('没有结果就不出卡片', () => {
  assert.equal(buildPlan({ form, result: null, reference: null, scope: 'public' }), null);
});

test('公开版：地名优先、无成本、价格待核定', () => {
  const plan = buildPlan({ form, result: publicResult, reference: null, scope: 'public' });
  assert.ok(plan);
  assert.equal(plan!.route.from, '广西 凭祥 友谊关');
  assert.equal(plan!.route.to, '河内 还剑郡');
  assert.equal(plan!.route.km, 302.8);
  assert.equal(plan!.vehicle.count, 1);
  assert.equal(plan!.vehicle.maxLoadTon, 26);
  assert.equal(plan!.cargo.weightTon, 25);
  assert.equal(plan!.cargo.typeLabel, '普通货物');
  assert.equal(plan!.price.status, 'pending');
  assert.equal(plan!.cost, null);
});

test('公开版：有区间时 status=estimate', () => {
  const r = { ...publicResult, price_low_vnd: 12_000_000, price_high_vnd: 15_000_000 };
  const plan = buildPlan({ form, result: r, reference: null, scope: 'public' })!;
  assert.equal(plan.price.status, 'estimate');
  assert.equal(plan.price.low, 12_000_000);
});

test('手填坐标没有地名时回落到坐标', () => {
  const f = { ...form, originLabel: undefined, destLabel: '' } as QuoteFormState;
  const plan = buildPlan({ form: f, result: publicResult, reference: null, scope: 'public' })!;
  assert.equal(plan.route.from, '22.100, 106.750');
  assert.equal(plan.route.to, '21.030, 105.850');
});

test('内部版：分项成本只出非零行，合计取 cost_total', () => {
  const internal = {
    route: { distance_km: 302.8, duration_h: 5.5, geometry: null },
    timing: { speed_factor: 1, adjusted_duration_h: 5.5, rest_hours: 0, loading_hours: 0, total_duration_h: 5.5 },
    breakdown: {
      cost_distance: 8_000_000,
      cost_time: 1_000_000,
      cost_fuel: 2_500_000,
      cost_loading: 0,
      cost_insurance: 0,
      cost_toll: 0,
      cost_misc: 0,
      cost_body_surcharge: 1_477_310.8,
      cost_restricted_zone: 0,
      cost_construction_zone: 0,
      cost_mountain_road: 0,
      cost_port: 0,
      cost_fixed: 0,
      cost_total: 12_977_310.8,
      cost_per_km: 42_857,
      cost_per_ton_km: null,
      capacity_ratio: 0.96,
      matched_vehicle_model_id: 'flatbed_13m',
      matched_vehicle_model_name: '普通平板 13米',
      vehicle_count: 1,
      cost_per_vehicle: 12_977_310.8,
    },
    suggestions: [],
    vehicle_count: 1,
  };
  const plan = buildPlan({ form, result: internal as never, reference: null, scope: 'internal' })!;
  assert.equal(plan.cost !== null, true);
  assert.deepEqual(
    plan.cost!.lines.map((l) => l.label),
    ['距离运费', '人工工时', '燃油', '车型附加'],
  );
  assert.equal(plan.cost!.total, 12_977_310.8);
  assert.equal(plan.price.status, 'cost');
});
